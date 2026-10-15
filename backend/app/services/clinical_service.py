import secrets
from datetime import datetime, timezone

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.clinical import icd10, vitals as vt
from app.core.errors import Conflict, Invalid, NotFound
from app.schemas.clinical import DiagnosisIn, DiagnosisUpdate, VitalsIn
from app.services import patient_service


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- vitals ------------------------------------------------------------------


async def record_vitals(db: AsyncDatabase, appt: dict, data: VitalsIn, actor: dict) -> dict:
    if appt["status"] in ("cancelled", "no_show"):
        raise Conflict("Cannot record vitals for a cancelled visit")
    patient = await patient_service.get_patient(db, appt["patient_id"])
    age = patient_service.current_age(patient)

    # Adults' height rarely changes: reuse the last one for BMI when not re-measured
    height, carried = data.height_cm, False
    if height is None and data.weight_kg is not None and (age is None or age >= 18):
        last = await db.vitals.find_one(
            {"patient_id": appt["patient_id"], "height_cm": {"$ne": None}}, sort=[("recorded_at", -1)]
        )
        if last:
            height, carried = last["height_cm"], True

    values = {
        "bp_systolic": data.bp_systolic,
        "bp_diastolic": data.bp_diastolic,
        "pulse": data.pulse,
        "temperature_c": data.temperature_c,
        "spo2": data.spo2,
        "weight_kg": data.weight_kg,
        "height_cm": data.height_cm,
        "bmi": vt.compute_bmi(data.weight_kg, height) if (age is None or age >= 18) else None,
    }
    doc = {
        "appointment_id": appt["_id"],
        "patient_id": appt["patient_id"],
        "doctor_id": appt["doctor_id"],
        **values,
        "height_carried_forward": carried,
        "flags": vt.flag_all(values, age),
        "note": data.note,
        "recorded_at": _now(),
        "recorded_by": actor["_id"],
        "recorded_by_role": actor["role"],
    }
    await db.vitals.insert_one(doc)

    critical = {k: f for k, f in doc["flags"].items() if f.startswith("critical")}
    # Summary on the appointment so queues and dashboards can highlight it
    await db.appointments.update_one(
        {"_id": appt["_id"]},
        {"$set": {"vitals_flag": "critical" if critical else "abnormal" if doc["flags"] else "normal"}},
    )
    if critical:
        readings = ", ".join(f"{vt.LABELS[k]} {values[k]:g} {vt.UNITS[k]}" for k in critical)
        await db.alerts.insert_one(
            {
                "type": "critical_vital",
                "patient_id": appt["patient_id"],
                "patient_name": appt["patient_name"],
                "appointment_id": appt["_id"],
                "doctor_id": appt["doctor_id"],
                "doctor_name": appt["doctor_name"],
                "session_id": None,
                "codes": list(critical),
                "message": f"Critical vitals for {appt['patient_name']}: {readings}",
                "created_at": doc["recorded_at"],
                "acknowledged_at": None,
                "acknowledged_by_role": None,
            }
        )
    return doc


async def visit_vitals(db: AsyncDatabase, appt: dict) -> list[dict]:
    return await db.vitals.find({"appointment_id": appt["_id"]}).sort("recorded_at", 1).to_list()


async def vitals_trend(db: AsyncDatabase, patient_id: str) -> dict:
    patient = await patient_service.get_patient(db, patient_id)
    if not patient:
        raise NotFound("Patient not found")
    age = patient_service.current_age(patient)
    readings = await db.vitals.find({"patient_id": patient["patient_id"]}).sort("recorded_at", 1).to_list(500)
    return {
        "patient_id": patient["patient_id"],
        "paediatric": age is not None and age < 18,
        "ranges": vt.ranges_for(age),
        "readings": readings,
    }


# --- examination & diagnoses -------------------------------------------------


async def get_notes(db: AsyncDatabase, appt: dict) -> dict:
    doc = await db.clinical_notes.find_one({"appointment_id": appt["_id"]})
    return doc or {
        "appointment_id": appt["_id"],
        "patient_id": appt["patient_id"],
        "examination": "",
        "examination_updated_at": None,
        "diagnoses": [],
        "changes": [],
    }


async def _update_notes(db: AsyncDatabase, appt: dict, update: dict, change: str, actor: dict) -> dict:
    update.setdefault("$set", {}).update({"updated_at": _now()})
    # First write creates the document: fill defaults for fields this update doesn't touch
    touched = {key.split(".")[0] for op in update.values() for key in op}
    defaults = {"examination": "", "examination_updated_at": None, "diagnoses": []}
    update["$setOnInsert"] = {
        "patient_id": appt["patient_id"],
        "doctor_id": appt["doctor_id"],
        **{k: v for k, v in defaults.items() if k not in touched},
    }
    update.setdefault("$push", {})["changes"] = {"change": change, "by_role": actor["role"], "by": actor["_id"], "at": _now()}
    return await db.clinical_notes.find_one_and_update(
        {"appointment_id": appt["_id"]}, update, upsert=True, return_document=ReturnDocument.AFTER
    )


async def save_examination(db: AsyncDatabase, appt: dict, text: str, dictated: bool, actor: dict) -> dict:
    change = "Examination findings updated" + (" (dictated)" if dictated else "")
    return await _update_notes(
        db, appt, {"$set": {"examination": text, "examination_updated_at": _now()}}, change, actor
    )


async def add_diagnosis(db: AsyncDatabase, appt: dict, data: DiagnosisIn, actor: dict) -> dict:
    code = icd10.lookup(data.code)
    if code is None:
        raise Invalid(f"Unknown ICD-10 code: {data.code}")
    notes = await get_notes(db, appt)
    if any(d["code"] == code.code for d in notes["diagnoses"]):
        raise Conflict(f"{code.code} is already recorded for this visit")
    now = _now()
    diagnosis = {
        "id": secrets.token_hex(6),
        "code": code.code,
        "title": code.title,
        "status": data.status,
        "note": data.note,
        "added_at": now,
        "updated_at": now,
    }
    return await _update_notes(
        db, appt, {"$push": {"diagnoses": diagnosis}}, f"Added {data.status} diagnosis {code.code} {code.title}", actor
    )


async def update_diagnosis(db: AsyncDatabase, appt: dict, diagnosis_id: str, data: DiagnosisUpdate, actor: dict) -> dict:
    notes = await get_notes(db, appt)
    current = next((d for d in notes["diagnoses"] if d["id"] == diagnosis_id), None)
    if current is None:
        raise NotFound("Diagnosis not found")
    sets = {"diagnoses.$.updated_at": _now()}
    changes = []
    if data.status and data.status != current["status"]:
        sets["diagnoses.$.status"] = data.status
        changes.append(f"marked {current['code']} {data.status}")
    if data.note is not None and data.note != current["note"]:
        sets["diagnoses.$.note"] = data.note
        changes.append(f"updated note on {current['code']}")
    if not changes:
        return notes
    await db.clinical_notes.update_one({"appointment_id": appt["_id"], "diagnoses.id": diagnosis_id}, {"$set": sets})
    summary = "; ".join(changes)
    return await _update_notes(db, appt, {}, summary[0].upper() + summary[1:], actor)


async def remove_diagnosis(db: AsyncDatabase, appt: dict, diagnosis_id: str, actor: dict) -> dict:
    notes = await get_notes(db, appt)
    current = next((d for d in notes["diagnoses"] if d["id"] == diagnosis_id), None)
    if current is None:
        raise NotFound("Diagnosis not found")
    return await _update_notes(
        db, appt, {"$pull": {"diagnoses": {"id": diagnosis_id}}}, f"Removed diagnosis {current['code']}", actor
    )

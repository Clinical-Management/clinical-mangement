import re
from datetime import date, datetime, timedelta, timezone

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.schemas.prescription import PrescriptionIn
from app.services import patient_service

# Allergy -> medicines in the same class (or with known cross-reactivity). Deliberately small and
# conservative: it prompts the doctor to check, it does not replace a drug-interaction database.
DRUG_CLASSES: dict[str, tuple[str, set[str]]] = {
    "penicillin": ("penicillin class", {"penicillin", "amoxicillin", "ampicillin", "cloxacillin", "piperacillin", "augmentin", "amoxyclav"}),
    "cephalosporin": ("possible cross-reactivity with penicillins", {"cefixime", "ceftriaxone", "cefuroxime", "cephalexin", "cefpodoxime", "cefadroxil"}),
    "sulfa": ("sulfonamide class", {"sulfamethoxazole", "cotrimoxazole", "co-trimoxazole", "septran", "sulfasalazine"}),
    "nsaid": ("NSAID class", {"ibuprofen", "diclofenac", "naproxen", "aspirin", "aceclofenac", "mefenamic", "ketorolac", "piroxicam"}),
}
ALLERGY_CLASS = {
    "penicillin": "penicillin",
    "amoxicillin": "penicillin",
    "ampicillin": "penicillin",
    "sulfa": "sulfa",
    "sulpha": "sulfa",
    "sulfonamide": "sulfa",
    "nsaid": "nsaid",
    "nsaids": "nsaid",
    "aspirin": "nsaid",
    "ibuprofen": "nsaid",
}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z-]+", text.lower()) if len(w) >= 4}


def allergy_warnings(medicines: list[dict], allergies: list[dict]) -> list[dict]:
    warnings = []
    for med in medicines:
        med_words = _words(med["name"])
        for allergy in allergies:
            substance = allergy["substance"]
            allergy_words = _words(substance)
            if med_words & allergy_words:
                warnings.append({"medicine": med["name"], "allergy": substance, "reason": "same substance"})
                continue
            for word in allergy_words:
                cls = ALLERGY_CLASS.get(word)
                if not cls:
                    continue
                checks = [(cls, DRUG_CLASSES[cls])]
                if cls == "penicillin":
                    checks.append(("cephalosporin", DRUG_CLASSES["cephalosporin"]))
                for _, (label, members) in checks:
                    if med_words & members:
                        warnings.append({"medicine": med["name"], "allergy": substance, "reason": label})
                        break
    return warnings


async def get(db: AsyncDatabase, appt: dict) -> dict:
    doc = await db.prescriptions.find_one({"appointment_id": appt["_id"]}) or {
        "medicines": [], "investigations": [], "advice": "", "follow_up": None, "summary_sections": {},
        "updated_at": None, "updated_by_role": None,
    }
    patient = await patient_service.get_patient(db, appt["patient_id"])
    allergies = (patient.get("medical") or {}).get("allergies", [])
    return {
        **doc,
        "appointment_id": str(appt["_id"]),
        "patient_id": appt["patient_id"],
        "allergy_warnings": allergy_warnings(doc["medicines"], allergies),
    }


async def save(db: AsyncDatabase, appt: dict, data: PrescriptionIn, actor: dict) -> dict:
    """Autosaved as a whole. A follow-up in N days gets its date filled in from the visit date."""
    body = data.model_dump(mode="json")
    follow = body.get("follow_up")
    if follow and follow.get("in_days") is not None and not follow.get("date"):
        follow["date"] = (date.fromisoformat(appt["date"]) + timedelta(days=follow["in_days"])).isoformat()
    await db.prescriptions.find_one_and_update(
        {"appointment_id": appt["_id"]},
        {
            "$set": {**body, "updated_at": datetime.now(timezone.utc), "updated_by": actor["_id"], "updated_by_role": actor["role"]},
            "$setOnInsert": {"patient_id": appt["patient_id"], "doctor_id": appt["doctor_id"]},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return await get(db, appt)

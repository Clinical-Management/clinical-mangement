"""Collect everything a case summary is built from, plus a fingerprint per source so we can
tell what changed since the summary was generated."""

import hashlib
import json
from datetime import date, timedelta
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.clinical.vitals import LABELS as VITAL_LABELS, UNITS as VITAL_UNITS
from app.services import patient_service

SECTIONS = [
    ("chief_complaint", "Chief complaint"),
    ("history", "History"),
    ("key_findings", "Key findings"),
    ("report_results", "Relevant report results"),
    ("diagnosis", "Diagnosis"),
    ("plan", "Plan"),
]
SECTION_KEYS = [k for k, _ in SECTIONS]

# Which sections each source feeds
SOURCE_SECTIONS = {
    "history": ["chief_complaint", "history"],
    "vitals": ["key_findings"],
    "examination": ["key_findings"],
    "reports": ["report_results"],
    "diagnoses": ["diagnosis"],
    "prescription": ["plan"],
}

REPORT_LOOKBACK_DAYS = 365


def _fp(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:16]


async def collect(db: AsyncDatabase, appt: dict) -> dict:
    """Structured context for writing the summary, and per-source fingerprints/labels."""
    patient = await patient_service.get_patient(db, appt["patient_id"])
    history = await db.history_sessions.find_one({"appointment_id": appt["_id"], "status": "submitted"})
    vitals = await db.vitals.find_one({"appointment_id": appt["_id"]}, sort=[("recorded_at", -1)])
    notes = await db.clinical_notes.find_one({"appointment_id": appt["_id"]}) or {}
    rx = await db.prescriptions.find_one({"appointment_id": appt["_id"]}) or {}

    since = (date.fromisoformat(appt["date"]) - timedelta(days=REPORT_LOOKBACK_DAYS)).isoformat()
    approved = await db.report_summaries.find(
        {"patient_id": appt["patient_id"], "status": "approved", "report_date": {"$gte": since}}
    ).sort("report_date", -1).to_list(50)
    visit_report_ids = {r["_id"] for r in await db.reports.find({"appointment_id": appt["_id"]}, {"_id": 1}).to_list(None)}

    history_ctx = None
    if history:
        fields = {k: f["value"] for k, f in history["fields"].items() if f["value"] and history["review"].get(k) != "rejected"}
        history_ctx = {"fields": fields, "summary": history.get("summary")}

    vitals_ctx = None
    if vitals:
        readings = []
        for key in ("bp", "pulse", "temperature_c", "spo2", "weight_kg", "bmi"):
            if key == "bp":
                if vitals.get("bp_systolic") is not None:
                    flag = vitals["flags"].get("bp_systolic") or vitals["flags"].get("bp_diastolic")
                    readings.append({"name": "BP", "value": f"{vitals['bp_systolic']}/{vitals['bp_diastolic']} mmHg", "flag": flag})
            elif vitals.get(key) is not None:
                readings.append({"name": VITAL_LABELS[key], "value": f"{vitals[key]:g} {VITAL_UNITS[key]}", "flag": vitals["flags"].get(key)})
        vitals_ctx = readings

    reports_ctx = []
    for s in approved:
        relevant = s["report_id"] in visit_report_ids or any(t["flag"] not in (None, "normal") for t in s["tests"]) or s.get("impression")
        if not relevant:
            continue
        reports_ctx.append(
            {
                "id": str(s["_id"]),
                "type": s["report_type"],
                "date": s["report_date"],
                "this_visit": s["report_id"] in visit_report_ids,
                "abnormal": [
                    {"name": t["name"], "value": t["value"], "unit": t["unit"], "flag": t["flag"], "range": t["reference_range"]}
                    for t in s["tests"]
                    if t["flag"] not in (None, "normal")
                ],
                "impression": s.get("impression"),
                "summary": s.get("summary_text"),
            }
        )

    context = {
        "patient": {"age": patient_service.current_age(patient), "gender": patient["gender"],
                    "allergies": [a["substance"] for a in (patient.get("medical") or {}).get("allergies", [])],
                    "chronic_conditions": [c["name"] for c in (patient.get("medical") or {}).get("chronic_conditions", [])]},
        "visit": {"date": appt["date"], "visit_type": appt["visit_type"], "doctor": appt["doctor_name"]},
        "history": history_ctx,
        "vitals": vitals_ctx,
        "examination": notes.get("examination") or None,
        "diagnoses": [{"code": d["code"], "title": d["title"], "status": d["status"]} for d in notes.get("diagnoses", [])],
        "reports": reports_ctx,
        "plan": {
            "medicines": rx.get("medicines", []),
            "investigations": rx.get("investigations", []),
            "advice": rx.get("advice") or None,
            "follow_up": rx.get("follow_up"),
        },
    }
    sources = {
        "history": {"fp": _fp(history_ctx), "present": history_ctx is not None},
        "vitals": {"fp": _fp(vitals_ctx), "present": vitals_ctx is not None},
        "examination": {"fp": _fp(context["examination"]), "present": bool(context["examination"])},
        "reports": {"fp": _fp(reports_ctx), "ids": {r["id"]: f"{r['type'].replace('_', ' ')} ({r['date']})" for r in reports_ctx}},
        "diagnoses": {"fp": _fp(context["diagnoses"]), "present": bool(context["diagnoses"])},
        "prescription": {"fp": _fp(context["plan"]), "present": any(context["plan"].values())},
    }
    return {"context": context, "sources": sources}


SOURCE_LABELS = {
    "history": "Pre-visit history",
    "vitals": "Vitals",
    "examination": "Examination notes",
    "diagnoses": "Diagnosis",
    "prescription": "Plan (prescription)",
}


def describe_changes(old: dict, new: dict) -> list[str]:
    """Human-readable list of what changed between two source snapshots."""
    changes = []
    for key in SOURCE_SECTIONS:
        if old.get(key, {}).get("fp") == new[key]["fp"]:
            continue
        if key == "reports":
            before, after = old.get("reports", {}).get("ids", {}), new["reports"]["ids"]
            changes += [f"New approved report: {after[i]}" for i in after if i not in before]
            changes += [f"Report no longer approved: {before[i]}" for i in before if i not in after]
            if not any(i not in before for i in after) and not any(i not in after for i in before):
                changes.append("Approved report results changed")
        elif not old.get(key, {}).get("present") and new[key].get("present"):
            changes.append(f"{SOURCE_LABELS[key]} added")
        else:
            changes.append(f"{SOURCE_LABELS[key]} changed")
    return changes


def affected_sections(old: dict, new: dict) -> set[str]:
    return {s for key, sections in SOURCE_SECTIONS.items() if old.get(key, {}).get("fp") != new[key]["fp"] for s in sections}

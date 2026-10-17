import logging
import secrets
from datetime import datetime, timezone
from typing import Any

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.ai.client import EngineError
from app.core.errors import Conflict, NotFound
from app.reports import labs
from app.reports.pages import cached_pages
from app.schemas.common import parse_object_id
from app.schemas.report import REPORT_TYPE_LABELS
from app.services import patient_service, report_service

log = logging.getLogger(__name__)

ASSISTIVE_LABEL = "Assistive, not diagnostic. Requires doctor review."
EDITABLE_TEST_FIELDS = ("name", "value", "unit", "reference_range")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- pages -------------------------------------------------------------------


async def report_pages(db: AsyncDatabase, report: dict, version: int | None = None) -> tuple[bytes, ...]:
    """Page images of a report version: the same images the AI reads and the viewer shows."""
    v = report_service._version(report, version)
    rendition = "processed" if v["kind"] in ("jpeg", "png") else "original"
    data, _, _ = await report_service.read_file(db, report, v["version"], rendition)
    key = str(v.get("processed_file_id") if rendition == "processed" and v.get("processed_file_id") else v["file_id"])
    return cached_pages(key, "image" if v["kind"] in ("jpeg", "png") else v["kind"], data)


# --- generation --------------------------------------------------------------


def _row(test: dict[str, Any], *, edited: bool = False, added: bool = False) -> dict:
    evaluated = labs.evaluate(
        test["name"], test.get("value"), test.get("unit"), test.get("reference_range"),
        test.get("ref_low"), test.get("ref_high"),
    )
    bbox = test.get("bbox")
    return {
        "id": test.get("id") or secrets.token_hex(5),
        "name": test["name"],
        "value": test.get("value"),
        "unit": test.get("unit"),
        "reference_range": test.get("reference_range"),
        "printed_flag": test.get("printed_flag"),
        "page": test.get("page"),
        "bbox": bbox if isinstance(bbox, list) and len(bbox) == 4 else None,
        "source_text": test.get("source_text"),
        # doctor-entered values carry no AI confidence
        "confidence": None if added else test.get("confidence"),
        **evaluated,
        # the AI may spot a flag the rules can't compute (non-numeric results)
        "flag": evaluated["flag"] or (_printed_to_flag(test.get("printed_flag"))),
        "edited": edited,
        "added_by_doctor": added,
    }


def _printed_to_flag(printed: str | None) -> str | None:
    p = (printed or "").strip().lower()
    return {"h": "high", "high": "high", "l": "low", "low": "low"}.get(p, "abnormal" if p in ("*", "abnormal") else None)


async def start(db: AsyncDatabase, report: dict) -> dict:
    """Create (or reset) the summary record for the report's current version; returns it.
    The AI run itself happens in `run` (in the background)."""
    patient = await patient_service.get_patient(db, report["patient_id"])
    consented = bool(patient and patient["consent"].get("ai_processing"))
    appt = report.get("appointment_id") and await db.appointments.find_one({"_id": report["appointment_id"]})
    now = _now()
    doc = {
        "report_id": report["_id"],
        "report_version": report["current_version"],
        "patient_id": report["patient_id"],
        "patient_name": report["patient_name"],
        "report_type": report["report_type"],
        "report_date": report["report_date"],
        "doctor_id": appt["doctor_id"] if appt else None,
        "doctor_name": appt["doctor_name"] if appt else None,
        "status": "processing" if consented else "no_consent",
        "error": None,
        "tests": [],
        "summary_text": None,
        "findings": None,
        "impression": None,
        "image_observation": None,
        "document_kind": None,
        "readability": None,
        "lab_name": None,
        "overall_confidence": None,
        "critical_values": [],
        "page_count": 0,
        "ai_generated": True,
        "edit_log": [],
        "approved_at": None,
        "approved_by": None,
        "approved_by_role": None,
        "created_at": now,
        "updated_at": now,
    }
    return await db.report_summaries.find_one_and_update(
        {"report_id": report["_id"], "report_version": report["current_version"]},
        {"$set": doc},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )


async def run(db: AsyncDatabase, summary_id, engine_factory) -> None:
    """Read the report with the AI, then apply deterministic flags and alert on critical values."""
    summary = await db.report_summaries.find_one({"_id": summary_id})
    if not summary or summary["status"] != "processing":
        return
    try:
        report = await db.reports.find_one({"_id": summary["report_id"]})
        pages = await report_pages(db, report, summary["report_version"])
        if not pages:
            raise EngineError("This file has no readable pages or image")
        patient = await patient_service.get_patient(db, report["patient_id"])
        result = await engine_factory().extract(
            list(pages),
            {
                "report_type_label": REPORT_TYPE_LABELS[report["report_type"]],
                "report_date": report["report_date"],
                "age": patient_service.current_age(patient),
                "gender": patient["gender"],
            },
        )
    except EngineError as exc:
        await db.report_summaries.update_one({"_id": summary_id}, {"$set": {"status": "failed", "error": str(exc), "updated_at": _now()}})
        return
    except Exception:
        log.exception("Report summarization failed")
        await db.report_summaries.update_one(
            {"_id": summary_id}, {"$set": {"status": "failed", "error": "Unexpected error while reading the report", "updated_at": _now()}}
        )
        return

    rows = [_row(t.model_dump()) for t in result.tests]
    critical = [f"{r['name']} {r['value']} {r['unit'] or ''}".strip() for r in rows if r["critical"]]
    await db.report_summaries.update_one(
        {"_id": summary_id},
        {
            "$set": {
                "status": "ready",
                "tests": rows,
                "summary_text": result.summary,
                "findings": result.findings,
                "impression": result.impression,
                "image_observation": result.image_observation,
                "document_kind": result.document_kind,
                "readability": result.readability,
                "lab_name": result.lab_name,
                "overall_confidence": result.overall_confidence,
                "critical_values": critical,
                "page_count": len(pages),
                "updated_at": _now(),
            }
        },
    )
    if critical:
        await _alert_critical(db, summary, critical)


async def _alert_critical(db: AsyncDatabase, summary: dict, critical: list[str]) -> None:
    report = await db.reports.find_one({"_id": summary["report_id"]})
    await db.alerts.insert_one(
        {
            "type": "critical_lab",
            "patient_id": summary["patient_id"],
            "patient_name": summary["patient_name"],
            "appointment_id": report.get("appointment_id"),
            "report_id": summary["report_id"],
            "doctor_id": summary["doctor_id"],
            "doctor_name": summary["doctor_name"] or "unassigned",
            "session_id": None,
            "codes": ["critical_lab"],
            "message": f"Critical lab value for {summary['patient_name']} (AI-read, verify): {'; '.join(critical)}",
            "created_at": _now(),
            "acknowledged_at": None,
            "acknowledged_by_role": None,
        }
    )


# --- reading & review --------------------------------------------------------


async def latest_for_report(db: AsyncDatabase, report: dict) -> dict | None:
    return await db.report_summaries.find_one({"report_id": report["_id"]}, sort=[("report_version", -1)])


async def get_summary(db: AsyncDatabase, summary_id: str, user: dict) -> tuple[dict, dict]:
    oid = parse_object_id(summary_id)
    summary = oid and await db.report_summaries.find_one({"_id": oid})
    if not summary:
        raise NotFound("Summary not found")
    report = await report_service.get_report(db, str(summary["report_id"]), user)
    return summary, report


def _ensure_editable(summary: dict) -> None:
    if summary["status"] not in ("ready", "approved"):
        raise Conflict("The summary is not ready yet")


async def _save(db: AsyncDatabase, summary: dict, sets: dict, log_entry: dict, user: dict) -> dict:
    # Any edit after approval needs re-approval, so unapproved changes never reach patients
    sets.update({"updated_at": _now(), "status": "ready", "approved_at": None, "approved_by": None, "approved_by_role": None})
    entry = {**log_entry, "by": user["_id"], "by_role": user["role"], "at": _now()}
    return await db.report_summaries.find_one_and_update(
        {"_id": summary["_id"]}, {"$set": sets, "$push": {"edit_log": entry}}, return_document=ReturnDocument.AFTER
    )


async def edit_test(db: AsyncDatabase, summary: dict, test_id: str, changes: dict, user: dict) -> dict:
    _ensure_editable(summary)
    rows = summary["tests"]
    index = next((i for i, r in enumerate(rows) if r["id"] == test_id), None)
    if index is None:
        raise NotFound("Result row not found")
    old = rows[index]
    updated = _row({**old, **{k: v for k, v in changes.items() if k in EDITABLE_TEST_FIELDS}}, edited=True, added=old["added_by_doctor"])
    updated["confidence"] = old["confidence"]
    rows = rows[:index] + [updated] + rows[index + 1 :]
    diff = {k: [old.get(k), updated.get(k)] for k in EDITABLE_TEST_FIELDS if old.get(k) != updated.get(k)}
    return await _save(db, summary, {"tests": rows}, {"field": f"test:{old['name']}", "action": "edit", "changes": diff}, user)


async def add_test(db: AsyncDatabase, summary: dict, values: dict, user: dict) -> dict:
    _ensure_editable(summary)
    row = _row({k: values.get(k) for k in EDITABLE_TEST_FIELDS}, added=True)
    return await _save(
        db, summary, {"tests": summary["tests"] + [row]},
        {"field": f"test:{row['name']}", "action": "add", "changes": {"value": [None, row["value"]]}}, user,
    )


async def remove_test(db: AsyncDatabase, summary: dict, test_id: str, user: dict) -> dict:
    _ensure_editable(summary)
    old = next((r for r in summary["tests"] if r["id"] == test_id), None)
    if old is None:
        raise NotFound("Result row not found")
    rows = [r for r in summary["tests"] if r["id"] != test_id]
    return await _save(db, summary, {"tests": rows}, {"field": f"test:{old['name']}", "action": "remove", "changes": {"value": [old["value"], None]}}, user)


async def edit_text(db: AsyncDatabase, summary: dict, changes: dict, user: dict) -> dict:
    _ensure_editable(summary)
    sets = {k: v for k, v in changes.items() if v is not None and v != summary.get(k)}
    if not sets:
        return summary
    diff = {k: [summary.get(k), v] for k, v in sets.items()}
    return await _save(db, summary, sets, {"field": ",".join(sets), "action": "edit", "changes": diff}, user)


async def approve(db: AsyncDatabase, summary: dict, user: dict) -> dict:
    _ensure_editable(summary)
    now = _now()
    return await db.report_summaries.find_one_and_update(
        {"_id": summary["_id"]},
        {
            "$set": {"status": "approved", "approved_at": now, "approved_by": user["_id"], "approved_by_role": user["role"], "updated_at": now},
            "$push": {"edit_log": {"field": "summary", "action": "approve", "changes": {}, "by": user["_id"], "by_role": user["role"], "at": now}},
        },
        return_document=ReturnDocument.AFTER,
    )


async def trends(db: AsyncDatabase, summary: dict) -> dict[str, list[dict]]:
    """For each analyte in this summary: values from the patient's approved summaries over time, plus this one."""
    keys = {r["analyte_key"] for r in summary["tests"] if r["value_numeric"] is not None}
    series: dict[str, list[dict]] = {k: [] for k in keys}
    others = await db.report_summaries.find(
        {"patient_id": summary["patient_id"], "status": "approved", "_id": {"$ne": summary["_id"]}}
    ).to_list(500)
    for s in others + [summary]:
        for r in s["tests"]:
            if r["analyte_key"] in series and r["value_numeric"] is not None:
                series[r["analyte_key"]].append(
                    {
                        "date": s["report_date"],
                        "value": r["value_numeric"],
                        "unit": r["unit"],
                        "flag": r["flag"],
                        "report_id": str(s["report_id"]),
                        "approved": s["status"] == "approved",
                        "current": s["_id"] == summary["_id"],
                    }
                )
    return {k: sorted(v, key=lambda p: p["date"]) for k, v in series.items()}


async def approved_summaries(db: AsyncDatabase, patient_id: str) -> list[dict]:
    """The only summaries that may flow into the case summary, prescriptions and the patient view."""
    return await db.report_summaries.find({"patient_id": patient_id, "status": "approved"}).sort("report_date", -1).to_list(200)

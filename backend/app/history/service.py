import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import settings
from app.core.errors import Conflict, Forbidden, Invalid, NotFound
from app.history import messages as msg
from app.history.engine import EngineError, HistoryEngine
from app.history.fields import FIELDS_BY_KEY, applicable_fields, select_template
from app.history.language import guess_language
from app.history.safety import RED_FLAGS, detect_red_flags, gives_medical_advice
from app.schemas.common import parse_object_id
from app.services import appointment_service, patient_service, scheduling_service

FRONT_DESK = {"admin", "receptionist"}
CLINICAL = {"admin", "doctor"}
ACTIVE_STATUSES = ("in_progress", "review")
OPEN_APPOINTMENT_STATUSES = ("scheduled", "waiting", "with_voicebot")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- access ------------------------------------------------------------------


async def get_session(db: AsyncDatabase, session_id: str) -> dict:
    oid = parse_object_id(session_id)
    doc = oid and await db.history_sessions.find_one({"_id": oid})
    if not doc:
        raise NotFound("History session not found")
    return doc


def check_link(doc: dict, token: str) -> None:
    """Kiosk / patient-phone links carry a secret token instead of a login."""
    if not doc.get("link_token_hash") or not secrets.compare_digest(doc["link_token_hash"], _hash(token)):
        raise NotFound("History session not found")
    if doc["link_expires_at"] < _now():
        raise Forbidden("This link has expired. Please ask the front desk for a new one.")


async def check_user_access(db: AsyncDatabase, doc: dict, user: dict, *, clinical: bool = False) -> None:
    """clinical=True: full history content (doctor of the visit, admin).
    Otherwise the patient-facing view, which the patient's own account may also open.
    Receptionists never see history content; they hand over a kiosk/phone link instead."""
    role = user["role"]
    if role == "admin" or (role == "doctor" and doc["doctor_id"] == user["_id"]):
        return
    if not clinical and role == "patient" and doc["patient_id"] in await appointment_service.managed_patient_ids(db, user):
        return
    raise NotFound("History session not found")


# --- context -----------------------------------------------------------------


async def _stored_data(db: AsyncDatabase, patient: dict) -> dict[str, str]:
    """What we already know: the last submitted history (doctor-reviewed values win) + the patient profile."""
    stored: dict[str, str] = {}
    last = await db.history_sessions.find_one(
        {"patient_id": patient["patient_id"], "status": "submitted"}, sort=[("submitted_at", -1)]
    )
    if last:
        for key, field in last["fields"].items():
            if FIELDS_BY_KEY[key].stable and field["value"] and last["review"].get(key) != "rejected":
                stored[key] = field["value"]

    medical = patient.get("medical") or {}
    profile = {
        "allergies": "; ".join(
            a["substance"] + (f" ({a['reaction']})" if a.get("reaction") else "") for a in medical.get("allergies", [])
        ),
        "past_medical_history": "; ".join(c["name"] for c in medical.get("chronic_conditions", [])),
        "current_medications": "; ".join(
            " ".join(filter(None, [m["name"], m.get("dosage"), m.get("frequency")]))
            for m in medical.get("current_medications", [])
        ),
    }
    for key, value in profile.items():
        if value and key not in stored:
            stored[key] = value
    return stored


def engine_context(doc: dict) -> dict[str, Any]:
    return {
        "template": doc["template"],
        "language": doc["language"],
        "language_mode": doc["language_mode"],
        "patient": doc["patient_context"],
        "returning": doc["returning"],
        "applicable_fields": doc["applicable_fields"],
        "stored": doc["stored"],
        "fields": {k: f["value"] for k, f in doc["fields"].items() if f["value"]},
        "transcript": [{"role": t["role"], "text": t["text"]} for t in doc["transcript"]],
    }


def _entry(role: str, text: str, language: str, input_mode: str | None = None) -> dict:
    return {"role": role, "text": text, "language": language, "input": input_mode, "at": _now()}


# --- lifecycle ---------------------------------------------------------------


def _issue_link() -> tuple[str, dict]:
    token = secrets.token_urlsafe(24)
    expires = _now() + timedelta(minutes=settings.history_link_minutes)
    return token, {"link_token_hash": _hash(token), "link_expires_at": expires}


def _check_consent(patient: dict, mode: str) -> None:
    consent = patient["consent"]
    if mode == "voice" and not patient_service.has_voicebot_consent(patient):
        raise Conflict("The patient has not consented to voice recording and AI processing")
    if mode == "text" and not (consent["data_storage"] and consent["ai_processing"]):
        raise Conflict("The patient has not consented to AI processing")


async def start_session(
    db: AsyncDatabase, *, appointment_id: str, mode: str, channel: str, language: str, actor: dict
) -> tuple[dict, str | None]:
    """Create (or resume) the history session for an appointment. Returns the session and,
    for kiosk / phone use, a one-off link token."""
    appt = await appointment_service.get_for_user(db, appointment_id, actor)
    if appt["status"] not in OPEN_APPOINTMENT_STATUSES:
        raise Conflict("History can only be taken before the consultation")
    if mode == "manual" and actor["role"] not in CLINICAL:
        raise Forbidden("Manual history entry is done by a doctor or admin")
    patient = await patient_service.get_patient(db, appt["patient_id"])
    _check_consent(patient, mode)

    wants_link = channel != "staff"
    existing = await db.history_sessions.find_one({"appointment_id": appt["_id"], "status": {"$in": list(ACTIVE_STATUSES)}})
    if existing:
        token, link = _issue_link() if wants_link else (None, {})
        doc = await db.history_sessions.find_one_and_update(
            {"_id": existing["_id"]},
            {"$set": {"mode": mode, "channel": channel, **link, "updated_at": _now()}},
            return_document=ReturnDocument.AFTER,
        )
        return doc, token

    doctor = await scheduling_service.get_doctor(db, appt["doctor_id"])
    age = patient_service.current_age(patient)
    returning = appt["visit_type"] != "new" or bool(
        await db.history_sessions.find_one({"patient_id": patient["patient_id"], "status": "submitted"})
    )
    template = select_template(doctor.get("specialization"), age)
    stored = await _stored_data(db, patient) if returning else {}
    keys = applicable_fields(template=template, age=age, gender=patient["gender"], returning=returning)
    lang = "en" if language == "auto" else language

    if mode == "manual":
        greeting = None
    elif language == "auto":
        greeting = msg.GREETING_RETURNING["en"] if returning else msg.GREETING_AUTO
    else:
        greeting = (msg.GREETING_RETURNING if returning else msg.GREETING)[lang]

    token, link = _issue_link() if wants_link else (None, {})
    now = _now()
    doc = {
        "appointment_id": appt["_id"],
        "patient_id": patient["patient_id"],
        "patient_name": patient["full_name"],
        "doctor_id": appt["doctor_id"],
        "doctor_name": appt["doctor_name"],
        "mode": mode,
        "channel": channel,
        "language": lang,
        "language_mode": "auto" if language == "auto" else "manual",
        "template": template,
        "returning": returning,
        "patient_context": {"age": age, "gender": patient["gender"], "first_name": patient["full_name"].split()[0]},
        "applicable_fields": keys,
        "stored": stored,
        # Known stable facts are pre-filled; the interview confirms them
        "fields": {k: {"value": stored.get(k, ""), "origin": "previous" if k in stored else None} for k in keys},
        "status": "in_progress",
        "transcript": [_entry("assistant", greeting, lang)] if greeting else [],
        "patient_summary": None,
        "summary": None,
        "summary_source": None,
        "red_flags": [],
        "review": {},
        "edit_log": [],
        **link,
        "created_at": now,
        "created_by": actor["_id"],
        "created_by_role": actor["role"],
        "submitted_at": None,
        "updated_at": now,
    }
    await db.history_sessions.insert_one(doc)

    await db.appointments.update_one(
        {"_id": appt["_id"]}, {"$set": {"history_session_id": doc["_id"], "history_status": "in_progress"}}
    )
    if mode != "manual":
        await _move_appointment(db, appt["_id"], "waiting", "with_voicebot")
    return doc, token


async def reissue_link(db: AsyncDatabase, doc: dict) -> tuple[dict, str]:
    if doc["status"] not in ACTIVE_STATUSES:
        raise Conflict("This history has already been completed")
    token, link = _issue_link()
    doc = await db.history_sessions.find_one_and_update(
        {"_id": doc["_id"]}, {"$set": link}, return_document=ReturnDocument.AFTER
    )
    return doc, token


async def _move_appointment(db: AsyncDatabase, appt_id: ObjectId, from_status: str, to_status: str) -> None:
    """Queue bookkeeping done by the voicebot itself (only if the appointment is where we expect)."""
    await db.appointments.update_one(
        {"_id": appt_id, "status": from_status},
        {
            "$set": {"status": to_status},
            "$push": {"status_history": {"status": to_status, "at": _now(), "by_role": "voicebot"}},
        },
    )


def _ensure_status(doc: dict, *allowed: str) -> None:
    if doc["status"] not in allowed:
        raise Conflict(
            {"escalated": "This history was stopped for urgent care.", "submitted": "This history is already submitted."}.get(
                doc["status"], "This action is not available right now."
            )
        )


async def _save(db: AsyncDatabase, doc: dict, update: dict) -> dict:
    update.setdefault("$set", {})["updated_at"] = _now()
    return await db.history_sessions.find_one_and_update({"_id": doc["_id"]}, update, return_document=ReturnDocument.AFTER)


def _apply_updates(doc: dict, updates, origin: str) -> dict:
    """$set operations for field updates, limited to the fields that apply to this patient."""
    sets = {}
    for u in updates:
        if u.key in doc["applicable_fields"] and u.value.strip():
            sets[f"fields.{u.key}"] = {"value": u.value.strip(), "origin": origin}
    return sets


# --- conversation ------------------------------------------------------------


async def _escalate(db: AsyncDatabase, doc: dict, flags: list[dict], *, source: str, patient_entry: dict) -> dict:
    now = _now()
    records = [
        {"code": f["code"], "label": RED_FLAGS[f["code"]]["label"], "source": source, "evidence": f["evidence"], "at": now}
        for f in flags
    ]
    # The urgent message must be in the language the patient just used, without waiting for the AI
    lang = doc["language"]
    if doc["language_mode"] == "auto":
        lang = guess_language(patient_entry["text"], lang)
    patient_entry["language"] = lang
    doc = await _save(
        db,
        doc,
        {
            "$set": {"status": "escalated", "language": lang},
            "$push": {
                "transcript": {"$each": [patient_entry, _entry("assistant", msg.URGENT[lang], lang)]},
                "red_flags": {"$each": records},
            },
        },
    )
    labels = ", ".join(dict.fromkeys(r["label"] for r in records))
    await db.alerts.insert_one(
        {
            "type": "red_flag",
            "patient_id": doc["patient_id"],
            "patient_name": doc["patient_name"],
            "appointment_id": doc["appointment_id"],
            "doctor_id": doc["doctor_id"],
            "doctor_name": doc["doctor_name"],
            "session_id": doc["_id"],
            "codes": [r["code"] for r in records],
            "message": f"Red flag for {doc['patient_name']}: {labels}",
            "created_at": now,
            "acknowledged_at": None,
            "acknowledged_by_role": None,
        }
    )
    await db.appointments.update_one(
        {"_id": doc["appointment_id"]}, {"$set": {"red_flag": True, "red_flag_labels": labels, "history_status": "escalated"}}
    )
    # Back in the queue, flagged, so staff can see the patient straight away
    await _move_appointment(db, doc["appointment_id"], "with_voicebot", "waiting")
    return doc


async def patient_message(db: AsyncDatabase, doc: dict, text: str, input_mode: str, engine_factory) -> dict:
    _ensure_status(doc, "in_progress")
    if doc["mode"] == "manual":
        raise Conflict("This history is being entered by staff")
    if input_mode == "voice":
        patient = await patient_service.get_patient(db, doc["patient_id"])
        if not patient_service.has_voicebot_consent(patient):
            raise Conflict("Voice input needs consent to voice recording; please type instead")

    entry = _entry("patient", text, doc["language"], input_mode)

    # Deterministic rules first: an emergency never waits on (or depends on) the AI
    if flags := detect_red_flags(text):
        return await _escalate(db, doc, flags, source="rules", patient_entry=entry)

    engine: HistoryEngine = engine_factory()
    ctx = engine_context(doc)
    ctx["transcript"].append({"role": "patient", "text": text})
    turn = await engine.next_turn(ctx)

    if turn.red_flags:
        return await _escalate(
            db, doc, [f.model_dump() for f in turn.red_flags], source="model", patient_entry=entry
        )

    language = turn.detected_language if doc["language_mode"] == "auto" else doc["language"]
    entry["language"] = language
    reply = msg.NO_ADVICE[language] if gives_medical_advice(turn.reply) else turn.reply
    sets = {**_apply_updates(doc, turn.field_updates, "patient"), "language": language}
    doc = await _save(
        db, doc, {"$set": sets, "$push": {"transcript": {"$each": [entry, _entry("assistant", reply, language)]}}}
    )
    if turn.interview_complete:
        doc = await finish(db, doc, engine_factory)
    return doc


async def set_language(db: AsyncDatabase, doc: dict, language: str) -> dict:
    _ensure_status(doc, "in_progress", "review")
    if language == "auto":
        return await _save(db, doc, {"$set": {"language_mode": "auto"}})
    return await _save(db, doc, {"$set": {"language": language, "language_mode": "manual"}})


async def finish(db: AsyncDatabase, doc: dict, engine_factory) -> dict:
    """End the interview and show the patient a summary to confirm."""
    _ensure_status(doc, "in_progress")
    review = await engine_factory().review(engine_context(doc), None)
    lang = doc["language"]
    return await _save(
        db,
        doc,
        {
            "$set": {**_apply_updates(doc, review.field_updates, "patient"), "status": "review", "patient_summary": review.patient_summary},
            "$push": {"transcript": _entry("assistant", msg.REVIEW_READY[lang], lang)},
        },
    )


async def correct(db: AsyncDatabase, doc: dict, text: str, input_mode: str, engine_factory) -> dict:
    """The patient corrects the read-back summary in their own words."""
    _ensure_status(doc, "review")
    entry = _entry("patient", text, doc["language"], input_mode)
    if flags := detect_red_flags(text):
        return await _escalate(db, doc, flags, source="rules", patient_entry=entry)
    review = await engine_factory().review(engine_context(doc), text)
    return await _save(
        db,
        doc,
        {
            "$set": {**_apply_updates(doc, review.field_updates, "patient"), "patient_summary": review.patient_summary},
            "$push": {"transcript": entry},
        },
    )


def fallback_summary(doc: dict) -> str:
    """Plain summary built from the fields when the AI is unavailable (and for manual entry)."""
    p = doc["patient_context"]
    lines = [f"{p['age'] if p['age'] is not None else '?'}y {p['gender']}. " + (
        f"Chief complaint: {doc['fields'].get('chief_complaint', {}).get('value') or 'not recorded'}."
    )]
    for key in doc["applicable_fields"]:
        value = doc["fields"][key]["value"]
        if key != "chief_complaint" and value:
            lines.append(f"{FIELDS_BY_KEY[key].label}: {value}")
    if doc["red_flags"]:
        lines.append("RED FLAGS: " + ", ".join(dict.fromkeys(r["label"] for r in doc["red_flags"])))
    return "\n".join(lines)


async def submit(db: AsyncDatabase, doc: dict, engine_factory) -> dict:
    if doc["mode"] == "manual":
        _ensure_status(doc, "in_progress", "review")
    else:
        _ensure_status(doc, "review")
    summary, source = None, "auto"
    if doc["mode"] != "manual":
        try:
            summary, source = await engine_factory().doctor_summary(engine_context(doc)), "ai"
        except EngineError:
            pass  # never block submission on the AI; fall back to a plain summary
    now = _now()
    review = {k: "pending" for k, f in doc["fields"].items() if f["value"]}
    doc = await _save(
        db,
        doc,
        {
            "$set": {
                "status": "submitted",
                "summary": summary or fallback_summary(doc),
                "summary_source": source,
                "review": review,
                "submitted_at": now,
                "link_expires_at": now,  # links stop working once submitted
            }
        },
    )
    await db.appointments.update_one({"_id": doc["appointment_id"]}, {"$set": {"history_status": "submitted"}})
    await _move_appointment(db, doc["appointment_id"], "with_voicebot", "waiting")
    return doc


# --- staff -------------------------------------------------------------------


async def save_manual(db: AsyncDatabase, doc: dict, fields: dict[str, str], actor: dict) -> dict:
    """Staff typing the history (voice/AI unavailable, or patient prefers). Takes over an active session."""
    _ensure_status(doc, "in_progress", "review")
    unknown = set(fields) - set(doc["applicable_fields"])
    if unknown:
        raise Invalid(f"Fields not applicable to this patient: {', '.join(sorted(unknown))}")
    sets = {f"fields.{k}": {"value": v.strip(), "origin": "staff"} for k, v in fields.items()}
    return await _save(db, doc, {"$set": {**sets, "mode": "manual", "status": "in_progress"}})


async def review_field(db: AsyncDatabase, doc: dict, key: str, action: str, value: str | None, actor: dict) -> dict:
    """Doctor accepts, rejects or edits one extracted field. Every action is logged."""
    _ensure_status(doc, "submitted")
    if key not in doc["applicable_fields"]:
        raise NotFound("Unknown field")
    old = doc["fields"][key]["value"]
    log = {"field": key, "action": action, "old": old, "new": old, "by": actor["_id"], "by_role": actor["role"], "at": _now()}
    sets: dict = {f"review.{key}": {"accept": "accepted", "reject": "rejected", "edit": "edited"}[action]}
    if action == "edit":
        if value is None:
            raise Invalid("A value is required to edit a field")
        sets[f"fields.{key}"] = {"value": value.strip(), "origin": "doctor"}
        log["new"] = value.strip()
    return await _save(db, doc, {"$set": sets, "$push": {"edit_log": log}})


async def edit_summary(db: AsyncDatabase, doc: dict, summary: str, actor: dict) -> dict:
    _ensure_status(doc, "submitted")
    log = {"field": "summary", "action": "edit", "old": doc["summary"], "new": summary, "by": actor["_id"], "by_role": actor["role"], "at": _now()}
    return await _save(db, doc, {"$set": {"summary": summary, "summary_source": "doctor"}, "$push": {"edit_log": log}})


async def list_sessions(db: AsyncDatabase, user: dict, *, appointment_id: str | None, patient_id: str | None) -> list[dict]:
    query: dict = {}
    if appointment_id:
        query["appointment_id"] = parse_object_id(appointment_id)
    if patient_id:
        query["patient_id"] = patient_id.upper()
    if user["role"] == "doctor":
        query["doctor_id"] = user["_id"]
    return await db.history_sessions.find(query).sort("created_at", -1).to_list(50)


# --- alerts ------------------------------------------------------------------


async def list_alerts(db: AsyncDatabase, user: dict, *, open_only: bool) -> list[dict]:
    query: dict = {"created_at": {"$gte": _now() - timedelta(hours=24)}}
    if open_only:
        query["acknowledged_at"] = None
    if user["role"] == "doctor":
        query["doctor_id"] = user["_id"]
    return await db.alerts.find(query).sort("created_at", -1).to_list(50)


async def acknowledge_alert(db: AsyncDatabase, alert_id: str, user: dict) -> dict:
    oid = parse_object_id(alert_id)
    query: dict = {"_id": oid}
    if user["role"] == "doctor":
        query["doctor_id"] = user["_id"]
    alert = oid and await db.alerts.find_one_and_update(
        query,
        {"$set": {"acknowledged_at": _now(), "acknowledged_by_role": user["role"], "acknowledged_by": user["_id"]}},
        return_document=ReturnDocument.AFTER,
    )
    if not alert:
        raise NotFound("Alert not found")
    return alert

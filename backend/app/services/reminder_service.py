"""Next appointment and reminders.

- the doctor's follow-up advice books the follow-up automatically (nearest free slot on or after the date)
- reminders go out on the clinic's schedule (e.g. 3 days, 1 day and 2 hours before) in the patient's
  language, with confirm and change/cancel links that work without signing in
- patients who haven't booked an advised follow-up get one nudge and appear on the front desk's callback list
- optional medicine and repeat-test reminders from a prescription

Dates and times are deterministic code on the clinic clock, never AI."""

import re
from datetime import date, datetime, time, timedelta, timezone

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from app.core import clock
from app.core.config import settings
from app.core.errors import Conflict, Invalid, NotFound
from app.notifications import templates as tpl
from app.schemas.appointment import AppointmentCreate, AppointmentStatus as S, RescheduleIn, Source
from app.services import appointment_service, messaging, notify_service, patient_service, scheduling_service

DEFAULT_SETTINGS = {"offsets_minutes": [3 * 24 * 60, 24 * 60, 120], "nudge_after_days": 1, "callback_window_days": 3}
SEARCH_DAYS = 21  # how far past the advised date to look for a free follow-up slot
PATIENT_LINK = {"_id": None, "role": "patient"}  # actor for changes made from a reminder link


def _now() -> datetime:
    return clock.clinic_now().astimezone(timezone.utc)


async def get_settings(db: AsyncDatabase) -> dict:
    doc = await db.settings.find_one({"_id": "reminders"}) or {}
    return {**DEFAULT_SETTINGS, **{k: v for k, v in doc.items() if k != "_id"}}


async def save_settings(db: AsyncDatabase, data: dict) -> dict:
    await db.settings.update_one({"_id": "reminders"}, {"$set": data}, upsert=True)
    return await get_settings(db)


def _start(appt: dict) -> datetime:
    """Clinic-local start of a booked appointment, as UTC."""
    h, m = map(int, appt["start_time"].split(":"))
    local = datetime.combine(date.fromisoformat(appt["date"]), time(h, m), tzinfo=clock.clinic_tz())
    return local.astimezone(timezone.utc)


async def _clinic(db: AsyncDatabase) -> dict:
    from app.services import prescription_service

    return await prescription_service.clinic_settings(db)


# --- links -------------------------------------------------------------------------------


async def manage_link(db: AsyncDatabase, appt: dict) -> str:
    """Signed link to the appointment page (valid until the day after the visit)."""
    days = max(1, (date.fromisoformat(appt["date"]) - clock.clinic_today()).days + 2)
    token = await messaging.issue_link_token(db, "appointment", appt["_id"], days)
    return f"{settings.frontend_url.rstrip('/')}/a/{appt['_id']}?t={token}"


async def appointment_for_link(db: AsyncDatabase, appointment_id: str, token: str) -> dict:
    oid = ObjectId(appointment_id) if ObjectId.is_valid(appointment_id) else None
    if not oid:
        raise NotFound("Appointment not found")
    await messaging.check_link_token(db, "appointment", oid, token)
    appt = await db.appointments.find_one({"_id": oid})
    if not appt:
        raise NotFound("Appointment not found")
    return appt


async def _message_values(db: AsyncDatabase, appt: dict, lang: str, link: str) -> dict:
    clinic = await _clinic(db)
    return {
        "clinic": clinic["name"], "patient": appt["patient_name"].split()[0], "doctor": appt["doctor_name"],
        "date": tpl.fmt_date(appt["date"], lang), "time": tpl.fmt_time(appt.get("start_time")),
        "confirm_link": f"{link}&do=confirm", "manage_link": link, "phone": clinic.get("phone") or "",
        "book_link": f"{settings.frontend_url.rstrip('/')}/login",
    }


# --- automatic follow-up booking ---------------------------------------------------------


async def suggest_slots(db: AsyncDatabase, doctor: dict, on_or_after: date, count: int = 3) -> list[dict]:
    """The nearest free slots from a date (skipping holidays, leave and full days)."""
    found = []
    day = max(on_or_after, clock.clinic_today())
    for _ in range(SEARCH_DAYS):
        slots = await scheduling_service.day_slots(db, doctor, day)
        for s in slots["slots"]:
            if s["status"] == "available":
                found.append({"date": day.isoformat(), "start_time": s["start"], "end_time": s["end"]})
                if len(found) >= count:
                    return found
        day += timedelta(days=1)
    return found


async def sync_follow_up(db: AsyncDatabase, appt: dict, follow_up_date: date | None, actor: dict) -> dict | None:
    """Called when a prescription is finalized: books (or moves, or cancels) the follow-up visit."""
    existing = await db.appointments.find_one({"follow_up_of": appt["_id"], "status": S.SCHEDULED.value})
    if follow_up_date is None:
        if existing:
            await appointment_service.cancel(db, existing, "Follow-up no longer advised", actor)
        return None
    if existing and existing["date"] == follow_up_date.isoformat():
        return existing
    # the patient may already have booked something with this doctor themselves
    own = await db.appointments.find_one({
        "patient_id": appt["patient_id"], "doctor_id": appt["doctor_id"], "status": S.SCHEDULED.value,
        "date": {"$gt": appt["date"]}, "_id": {"$ne": existing and existing["_id"]},
    })
    if own and not existing:
        return own
    doctor = await scheduling_service.get_doctor(db, appt["doctor_id"])
    for slot in await suggest_slots(db, doctor, follow_up_date, count=5):
        try:
            if existing:
                moved = await appointment_service.reschedule(
                    db, existing, RescheduleIn(date=date.fromisoformat(slot["date"]), start_time=slot["start_time"]), actor
                )
                return moved
            booked = await appointment_service.book(
                db, AppointmentCreate(patient_id=appt["patient_id"], doctor_id=str(appt["doctor_id"]), date=date.fromisoformat(slot["date"]),
                                      start_time=slot["start_time"]),
                actor, source=Source.FOLLOW_UP,
            )
            await db.appointments.update_one({"_id": booked["_id"]}, {"$set": {"follow_up_of": appt["_id"]}})
            booked["follow_up_of"] = appt["_id"]
            await _announce_follow_up(db, booked)
            return booked
        except Conflict:
            continue  # taken a moment ago, or the patient has a visit that day: try the next slot
    return None


async def _announce_follow_up(db: AsyncDatabase, appt: dict) -> None:
    patient = await patient_service.get_patient(db, appt["patient_id"])
    p = notify_service.prefs(patient)
    if not p["reminders"]:
        return
    values = await _message_values(db, appt, p["language"], await manage_link(db, appt))
    await notify_service.queue(db, patient, kind="follow_up_booked", text=tpl.render("follow_up_booked", p["language"], **values), appointment_id=appt["_id"])


# --- scheduled reminders ------------------------------------------------------------------


async def queue_due_reminders(db: AsyncDatabase) -> int:
    """For each booked appointment, the reminder whose time has come (only the latest one if several are
    due, e.g. for a visit booked yesterday for tomorrow). Re-running is harmless."""
    cfg = await get_settings(db)
    offsets = sorted(cfg["offsets_minutes"])
    if not offsets:
        return 0
    now = _now()
    today = clock.clinic_today()
    horizon = today + timedelta(days=max(offsets) // (24 * 60) + 2)
    queued = 0
    async for appt in db.appointments.find({
        "status": S.SCHEDULED.value, "start_time": {"$ne": None}, "date": {"$gte": today.isoformat(), "$lte": horizon.isoformat()},
    }):
        start = _start(appt)
        if start <= now:
            continue
        due = [o for o in offsets if start - timedelta(minutes=o) <= now]
        sent = set(appt.get("reminders_sent", []))
        if not due or min(due) in sent:
            continue
        # claim it first, so two workers never both send
        claimed = await db.appointments.update_one(
            {"_id": appt["_id"], "reminders_sent": {"$ne": min(due)}}, {"$addToSet": {"reminders_sent": {"$each": due}}}
        )
        if not claimed.modified_count:
            continue
        created = appt.get("created_at")
        if created and (created if created.tzinfo else created.replace(tzinfo=timezone.utc)) > now - timedelta(minutes=30):
            continue  # just booked: they know
        patient = await patient_service.get_patient(db, appt["patient_id"])
        p = notify_service.prefs(patient)
        if not p["reminders"]:
            continue
        values = await _message_values(db, appt, p["language"], await manage_link(db, appt))
        await notify_service.queue(db, patient, kind="reminder", text=tpl.render("reminder", p["language"], **values),
                                   appointment_id=appt["_id"], ref={"offset_minutes": min(due)})
        queued += 1
    return queued


# --- follow-ups not booked: nudges and the callback list ------------------------------------


async def _advised_follow_ups(db: AsyncDatabase, *, due_by: date, doctor_id: ObjectId | None = None) -> list[dict]:
    """Finalized prescriptions with a follow-up date up to `due_by` where no later visit with that doctor is
    booked or done."""
    out = []
    query = {"status": "final", "follow_up.date": {"$lte": due_by.isoformat()}}
    async for rx in db.prescriptions.find(query):
        visit = await db.appointments.find_one({"_id": rx["appointment_id"]})
        if not visit or (doctor_id and visit["doctor_id"] != doctor_id):
            continue
        later = await db.appointments.find_one({
            "patient_id": visit["patient_id"], "doctor_id": visit["doctor_id"], "date": {"$gt": visit["date"]},
            "status": {"$in": [S.SCHEDULED.value, S.WAITING.value, S.WITH_VOICEBOT.value, S.IN_CONSULTATION.value, S.COMPLETED.value]},
        })
        if later:
            continue
        out.append({"rx": rx, "visit": visit, "due": str(rx["follow_up"]["date"])[:10]})
    return out


async def queue_follow_up_nudges(db: AsyncDatabase) -> int:
    cfg = await get_settings(db)
    today = clock.clinic_today()
    queued = 0
    for item in await _advised_follow_ups(db, due_by=today - timedelta(days=cfg["nudge_after_days"])):
        rx, visit = item["rx"], item["visit"]
        if rx.get("nudged_at"):
            continue
        claimed = await db.prescriptions.update_one({"_id": rx["_id"], "nudged_at": None}, {"$set": {"nudged_at": _now()}})
        if not claimed.modified_count:
            continue
        patient = await patient_service.get_patient(db, visit["patient_id"])
        p = notify_service.prefs(patient)
        if not p["reminders"]:
            continue
        values = await _message_values(db, {**visit, "date": item["due"]}, p["language"], "")
        await notify_service.queue(db, patient, kind="follow_up_nudge", text=tpl.render("follow_up_nudge", p["language"], **values),
                                   appointment_id=visit["_id"])
        queued += 1
    return queued


async def callback_list(db: AsyncDatabase, include_closed: bool = False) -> list[dict]:
    """Patients to phone: an advised follow-up is due within a few days (or overdue) and nothing is booked."""
    cfg = await get_settings(db)
    today = clock.clinic_today()
    rows = []
    for item in await _advised_follow_ups(db, due_by=today + timedelta(days=cfg["callback_window_days"])):
        visit = item["visit"]
        call = await db.callbacks.find_one({"appointment_id": visit["_id"]}, sort=[("at", -1)])
        if call and call["outcome"] in ("declined", "not_needed") and not include_closed:
            continue
        patient = await patient_service.get_patient(db, visit["patient_id"])
        rows.append({
            "appointment_id": str(visit["_id"]), "patient_id": visit["patient_id"], "patient_name": patient["full_name"],
            "phone": patient["phone"], "doctor_id": str(visit["doctor_id"]), "doctor_name": visit["doctor_name"], "visit_date": visit["date"],
            "follow_up_date": item["due"], "overdue_days": (today - date.fromisoformat(item["due"])).days,
            "nudged": bool(item["rx"].get("nudged_at")),
            "last_call": call and {"outcome": call["outcome"], "note": call.get("note"), "at": call["at"], "by_role": call["by_role"]},
        })
    return sorted(rows, key=lambda r: r["follow_up_date"])


async def record_call(db: AsyncDatabase, appointment_id: str, outcome: str, note: str | None, actor: dict) -> dict:
    oid = ObjectId(appointment_id) if ObjectId.is_valid(appointment_id) else None
    if not oid or not await db.appointments.find_one({"_id": oid}):
        raise NotFound("Visit not found")
    doc = {"appointment_id": oid, "outcome": outcome, "note": note, "at": _now(), "by": actor["_id"], "by_role": actor["role"]}
    await db.callbacks.insert_one(doc)
    return doc


async def follow_ups_due(db: AsyncDatabase, doctor_id: ObjectId | None, *, days: int = 7) -> dict:
    """For dashboards: follow-up visits booked in the next `days`, and advised ones that are overdue."""
    today = clock.clinic_today()
    q = {"source": Source.FOLLOW_UP.value, "status": S.SCHEDULED.value, "date": {"$gte": today.isoformat(), "$lte": (today + timedelta(days=days)).isoformat()}}
    if doctor_id:
        q["doctor_id"] = doctor_id
    booked = await db.appointments.find(q, {"patient_id": 1, "patient_name": 1, "doctor_name": 1, "date": 1, "start_time": 1}).sort([("date", 1), ("start_time", 1)]).to_list(200)
    overdue = [
        {"appointment_id": str(i["visit"]["_id"]), "patient_id": i["visit"]["patient_id"], "patient_name": i["visit"]["patient_name"],
         "doctor_name": i["visit"]["doctor_name"], "follow_up_date": i["due"], "overdue_days": (today - date.fromisoformat(i["due"])).days}
        for i in await _advised_follow_ups(db, due_by=today - timedelta(days=1), doctor_id=doctor_id)
    ]
    return {"booked": [{**{k: v for k, v in b.items() if k != "_id"}, "id": str(b["_id"])} for b in booked], "overdue": overdue}


# --- medicine and repeat-test reminders ------------------------------------------------------

_TIMES = {"morning": "08:00", "afternoon": "14:00", "night": "20:00"}
_ABBR = {"od": ["08:00"], "once": ["08:00"], "bd": ["08:00", "20:00"], "bid": ["08:00", "20:00"], "twice": ["08:00", "20:00"],
         "tds": ["08:00", "14:00", "20:00"], "tid": ["08:00", "14:00", "20:00"], "thrice": ["08:00", "14:00", "20:00"],
         "qid": ["08:00", "12:00", "16:00", "20:00"], "hs": ["21:00"], "at night": ["21:00"], "bedtime": ["21:00"]}


def dose_times(frequency: str | None) -> list[str]:
    """'1-0-1' -> 08:00, 20:00; 'BD' -> 08:00, 20:00; 'SOS' / unknown -> none (no reminder)."""
    f = (frequency or "").strip().lower()
    if m := re.fullmatch(r"([0-9½.]+)\s*-\s*([0-9½.]+)\s*-\s*([0-9½.]+)", f):
        return [t for t, part in zip(_TIMES.values(), m.groups()) if part not in ("0", "0.0")]
    for key, times in _ABBR.items():
        if re.search(rf"\b{key}\b", f):
            return times
    return []


def duration_days(duration: str | None) -> int:
    """'5 days' -> 5, '2 weeks' -> 14, '1 month' -> 30 (capped at 30); unknown -> 0."""
    m = re.search(r"(\d+)\s*(day|week|month|d\b|w\b)", (duration or "").lower())
    if not m:
        return 0
    n, unit = int(m.group(1)), m.group(2)
    return min(30, n * (7 if unit.startswith("w") else 30 if unit.startswith("m") else 1))


async def schedule_medicine_reminders(db: AsyncDatabase, version: dict, actor: dict) -> int:
    """App (and WhatsApp, if the patient uses it) reminders at dose times for each medicine's duration."""
    await cancel_medicine_reminders(db, version)
    patient = await patient_service.get_patient(db, version["patient_id"])
    p = notify_service.prefs(patient)
    channels = ["app"] + (["whatsapp"] if "whatsapp" in p["channels"] else [])
    start = date.fromisoformat(version["visit_date"]) if version["visit_date"] >= clock.clinic_today().isoformat() else clock.clinic_today()
    slots: dict[datetime, list[str]] = {}
    for med in version["content"]["medicines"]:
        times, days = dose_times(med.get("frequency")), duration_days(med.get("duration"))
        for d in range(days):
            for t in times:
                h, m = map(int, t.split(":"))
                at = datetime.combine(start + timedelta(days=d), time(h, m), tzinfo=clock.clinic_tz()).astimezone(timezone.utc)
                if at > _now():
                    slots.setdefault(at, []).append(" ".join(filter(None, [med["name"], med.get("dose")])))
    if not slots:
        raise Invalid("None of the medicines has a regular schedule and duration to remind about")
    clinic = (await _clinic(db))["name"]
    for at, meds in sorted(slots.items()):
        text = tpl.render("medicine", p["language"], clinic=clinic, patient=patient["full_name"].split()[0], medicines=", ".join(meds))
        await notify_service.queue(db, patient, kind="medicine", text=text, channels=channels, at=at,
                                   appointment_id=version["appointment_id"], ref={"version_id": version["_id"]})
    await db.prescription_versions.update_one({"_id": version["_id"]}, {"$set": {"medicine_reminders": {"on": True, "count": len(slots), "by_role": actor["role"]}}})
    return len(slots)


async def cancel_medicine_reminders(db: AsyncDatabase, version: dict) -> None:
    await notify_service.cancel(db, {"kind": "medicine", "ref.version_id": version["_id"]})
    await db.prescription_versions.update_one({"_id": version["_id"]}, {"$set": {"medicine_reminders": {"on": False}}})


async def schedule_test_reminder(db: AsyncDatabase, version: dict, on: date, tests: list[str]) -> dict:
    if on <= clock.clinic_today():
        raise Invalid("Choose a future date")
    patient = await patient_service.get_patient(db, version["patient_id"])
    p = notify_service.prefs(patient)
    at = datetime.combine(on, time(9, 0), tzinfo=clock.clinic_tz()).astimezone(timezone.utc)
    text = tpl.render("repeat_test", p["language"], clinic=(await _clinic(db))["name"], patient=patient["full_name"].split()[0], tests=", ".join(tests))
    docs = await notify_service.queue(db, patient, kind="repeat_test", text=text, at=at, appointment_id=version["appointment_id"],
                                      ref={"version_id": version["_id"]})
    return {"date": on.isoformat(), "tests": tests, "messages": len(docs)}


# --- worker entry ----------------------------------------------------------------------------


async def queue_due(db: AsyncDatabase) -> None:
    await queue_due_reminders(db)
    await queue_follow_up_nudges(db)

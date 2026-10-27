from datetime import date, datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core import clock
from app.core.errors import Conflict, Forbidden, Invalid, NotFound
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentStatus as S,
    PaymentStatus,
    RescheduleIn,
    Source,
    VisitType,
    VisitTypeOverrideIn,
    WalkInCreate,
)
from app.schemas.common import parse_object_id
from app.services import patient_service, scheduling_service

FRONT_DESK = {"admin", "receptionist"}

# Statuses shown on the live queue, in display order
QUEUE_STATUSES = [S.IN_CONSULTATION, S.WITH_VOICEBOT, S.WAITING, S.COMPLETED]

# Allowed moves on the queue (check-in and cancel have their own endpoints)
TRANSITIONS: dict[S, set[S]] = {
    S.SCHEDULED: {S.NO_SHOW},
    S.WAITING: {S.WITH_VOICEBOT, S.IN_CONSULTATION, S.NO_SHOW},
    S.WITH_VOICEBOT: {S.WAITING, S.IN_CONSULTATION},
    S.IN_CONSULTATION: {S.COMPLETED},
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _slot_key(doctor_oid: ObjectId, day: date, start: str) -> str:
    return f"{doctor_oid}|{day.isoformat()}|{start}"


def _event(status: S, actor: dict) -> dict:
    return {"status": status.value, "at": _now(), "by_role": actor["role"]}


# --- access ------------------------------------------------------------------


async def managed_patient_ids(db: AsyncDatabase, user: dict) -> list[str]:
    return [p["patient_id"] for p in await patient_service.list_managed(db, user["_id"])]


async def _patient_for(db: AsyncDatabase, patient_id: str, user: dict) -> dict:
    patient = await patient_service.get_patient(db, patient_id)
    if patient is None or (user["role"] == "patient" and patient.get("managed_by") != user["_id"]):
        raise NotFound("Patient not found")
    return patient


async def get_for_user(db: AsyncDatabase, appointment_id: str, user: dict) -> dict:
    """Front desk sees everything, doctors their own appointments, patients their family's."""
    oid = parse_object_id(appointment_id)
    appt = oid and await db.appointments.find_one({"_id": oid})
    if appt:
        if user["role"] == "doctor" and appt["doctor_id"] == user["_id"]:
            return appt
        if user["role"] == "patient" and appt["patient_id"] in await managed_patient_ids(db, user):
            return appt
        if user["role"] in FRONT_DESK:
            return appt
    raise NotFound("Appointment not found")


# --- visit type --------------------------------------------------------------

# a partly paid visit was still charged, so it anchors the follow-up window
PAID_STATUSES = [PaymentStatus.PAID.value, PaymentStatus.PARTIAL.value]


async def compute_visit_type(
    db: AsyncDatabase, patient_id: str, doctor: dict, day: date, exclude: ObjectId | None = None
) -> dict:
    """New: no earlier completed visit with this doctor.
    Follow-up: within the doctor's follow-up window of the last *paid* standard (new or returning) visit,
    and, if the doctor limits them, fewer follow-ups since then than allowed.
    Returning: anything else.
    A paid follow-up doesn't restart the window; only a visit charged at the standard rate does."""
    prior: dict = {
        "patient_id": patient_id,
        "doctor_id": doctor["_id"],
        "status": S.COMPLETED.value,
        "date": {"$lte": day.isoformat()},
    }
    if exclude:
        prior["_id"] = {"$ne": exclude}
    last = await db.appointments.find_one(prior, sort=[("date", -1)])
    last_paid = await db.appointments.find_one(
        {**prior, "payment_status": {"$in": PAID_STATUSES}, "visit_type": {"$ne": VisitType.FOLLOW_UP.value}}, sort=[("date", -1)]
    )
    follow_ups_used = 0
    if last_paid:
        follow_ups_used = await db.appointments.count_documents(
            {**prior, "visit_type": VisitType.FOLLOW_UP.value, "date": {"$gt": last_paid["date"], "$lte": day.isoformat()}}
        )
    allowed = doctor.get("free_follow_ups")

    if last is None:
        visit_type = VisitType.NEW
    elif (
        last_paid
        and (day - date.fromisoformat(last_paid["date"])).days <= doctor["follow_up_days"]
        and (allowed is None or follow_ups_used < allowed)
    ):
        visit_type = VisitType.FOLLOW_UP
    else:
        visit_type = VisitType.RETURNING
    return {
        "visit_type": visit_type,
        "last_visit_date": last and last["date"],
        "last_paid_visit_date": last_paid and last_paid["date"],
        "follow_up_days": doctor["follow_up_days"],
        "follow_ups_used": follow_ups_used,
        "free_follow_ups": allowed,
    }


async def _refresh_visit_type(db: AsyncDatabase, appt: dict, doctor: dict, day: date) -> dict:
    """Fields to $set after the date changes; a front-desk override always wins."""
    auto = (await compute_visit_type(db, appt["patient_id"], doctor, day, exclude=appt["_id"]))["visit_type"].value
    override = appt.get("visit_type_override")
    return {"visit_type_auto": auto, "visit_type": override["visit_type"] if override else auto}


# --- booking -----------------------------------------------------------------


async def _ensure_no_same_day_booking(db: AsyncDatabase, patient_id: str, doctor_oid: ObjectId, day: date) -> None:
    active = [s.value for s in (S.SCHEDULED, S.WAITING, S.WITH_VOICEBOT, S.IN_CONSULTATION)]
    if await db.appointments.find_one(
        {"patient_id": patient_id, "doctor_id": doctor_oid, "date": day.isoformat(), "status": {"$in": active}}
    ):
        raise Conflict("This patient already has an appointment with this doctor on that day")


async def _next_token(db: AsyncDatabase, doctor_oid: ObjectId, day: date) -> int:
    counter = await db.counters.find_one_and_update(
        {"_id": f"token:{doctor_oid}:{day.isoformat()}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return counter["seq"]


async def _new_appointment(db, *, patient: dict, doctor: dict, day: date, actor: dict, source: Source) -> dict:
    visit = await compute_visit_type(db, patient["patient_id"], doctor, day)
    return {
        "patient_id": patient["patient_id"],
        "patient_name": patient["full_name"],
        "doctor_id": doctor["_id"],
        "doctor_name": doctor["full_name"],
        "date": day.isoformat(),
        "start_time": None,
        "end_time": None,
        "source": source.value,
        "token": None,
        "checked_in_at": None,
        "visit_type": visit["visit_type"].value,
        "visit_type_auto": visit["visit_type"].value,
        "visit_type_override": None,
        "payment_status": PaymentStatus.UNPAID.value,
        "reschedule_history": [],
        "created_at": _now(),
        "created_by": actor["_id"],
    }


async def book(db: AsyncDatabase, data: AppointmentCreate, actor: dict, source: Source | None = None) -> dict:
    patient = await _patient_for(db, data.patient_id, actor)
    doctor = await scheduling_service.get_doctor(db, data.doctor_id)
    end = await scheduling_service.validate_slot(db, doctor, data.date, data.start_time)
    await _ensure_no_same_day_booking(db, patient["patient_id"], doctor["_id"], data.date)

    source = source or (Source.ONLINE if actor["role"] == "patient" else Source.FRONT_DESK)
    doc = await _new_appointment(db, patient=patient, doctor=doctor, day=data.date, actor=actor, source=source)
    doc.update(
        start_time=data.start_time,
        end_time=end,
        slot_key=_slot_key(doctor["_id"], data.date, data.start_time),
        status=S.SCHEDULED.value,
        status_history=[_event(S.SCHEDULED, actor)],
    )
    try:
        await db.appointments.insert_one(doc)
    except DuplicateKeyError:
        raise Conflict("This slot has just been booked. Please choose another time.")
    return doc


async def walk_in(db: AsyncDatabase, data: WalkInCreate, actor: dict) -> dict:
    """Walk-ins skip slots: they join today's queue straight away with a token."""
    patient = await _patient_for(db, data.patient_id, actor)
    doctor = await scheduling_service.get_doctor(db, data.doctor_id)
    today = clock.clinic_today()
    if reason := await scheduling_service.unavailable_reason(db, doctor["_id"], today):
        raise Conflict(reason)
    await _ensure_no_same_day_booking(db, patient["patient_id"], doctor["_id"], today)

    doc = await _new_appointment(db, patient=patient, doctor=doctor, day=today, actor=actor, source=Source.WALK_IN)
    doc.update(
        status=S.WAITING.value,
        token=await _next_token(db, doctor["_id"], today),
        checked_in_at=_now(),
        status_history=[_event(S.WAITING, actor)],
    )
    await db.appointments.insert_one(doc)
    return doc


async def check_in(db: AsyncDatabase, appt: dict, actor: dict) -> dict:
    if appt["status"] != S.SCHEDULED.value:
        raise Conflict("Only scheduled appointments can be checked in")
    today = clock.clinic_today()
    if appt["date"] != today.isoformat():
        raise Conflict("Appointments can only be checked in on their own date")
    doctor = await scheduling_service.get_doctor(db, appt["doctor_id"])
    return await db.appointments.find_one_and_update(
        {"_id": appt["_id"], "status": S.SCHEDULED.value},
        {
            "$set": {
                "status": S.WAITING.value,
                "token": await _next_token(db, doctor["_id"], today),
                "checked_in_at": _now(),
                # payments may have changed since booking
                **await _refresh_visit_type(db, appt, doctor, today),
            },
            "$push": {"status_history": _event(S.WAITING, actor)},
        },
        return_document=ReturnDocument.AFTER,
    )


def _ensure_patient_may_change(appt: dict, actor: dict) -> None:
    if actor["role"] == "patient" and appt["source"] == Source.WALK_IN.value:
        raise Forbidden("Please ask the front desk to change a walk-in visit")


async def reschedule(db: AsyncDatabase, appt: dict, data: RescheduleIn, actor: dict) -> dict:
    if appt["status"] != S.SCHEDULED.value:
        raise Conflict("Only scheduled appointments can be rescheduled")
    _ensure_patient_may_change(appt, actor)
    doctor = await scheduling_service.get_doctor(db, appt["doctor_id"])
    end = await scheduling_service.validate_slot(db, doctor, data.date, data.start_time)
    if data.date.isoformat() != appt["date"]:
        await _ensure_no_same_day_booking(db, appt["patient_id"], doctor["_id"], data.date)

    history = {
        "from_date": appt["date"],
        "from_time": appt["start_time"],
        "to_date": data.date.isoformat(),
        "to_time": data.start_time,
        "at": _now(),
        "by_role": actor["role"],
    }
    try:
        # Replacing slot_key frees the old slot and claims the new one in a single write
        return await db.appointments.find_one_and_update(
            {"_id": appt["_id"], "status": S.SCHEDULED.value},
            {
                "$set": {
                    "date": data.date.isoformat(),
                    "start_time": data.start_time,
                    "end_time": end,
                    "slot_key": _slot_key(doctor["_id"], data.date, data.start_time),
                    **await _refresh_visit_type(db, appt, doctor, data.date),
                },
                "$push": {"reschedule_history": history},
            },
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        raise Conflict("This slot has just been booked. Please choose another time.")


async def cancel(db: AsyncDatabase, appt: dict, reason: str | None, actor: dict) -> dict:
    allowed = {S.SCHEDULED.value} if actor["role"] == "patient" else {S.SCHEDULED.value, S.WAITING.value}
    if appt["status"] not in allowed:
        raise Conflict("This appointment can no longer be cancelled")
    _ensure_patient_may_change(appt, actor)
    return await db.appointments.find_one_and_update(
        {"_id": appt["_id"], "status": {"$in": list(allowed)}},
        {
            "$set": {"status": S.CANCELLED.value, "cancel_reason": reason, "cancelled_at": _now()},
            "$unset": {"slot_key": ""},  # releases the slot
            "$push": {"status_history": _event(S.CANCELLED, actor)},
        },
        return_document=ReturnDocument.AFTER,
    )


async def set_status(db: AsyncDatabase, appt: dict, new: S, actor: dict) -> dict:
    current = S(appt["status"])
    if new not in TRANSITIONS.get(current, set()):
        raise Conflict(f"Cannot move from {current.value} to {new.value}")
    if new == S.WITH_VOICEBOT:
        patient = await patient_service.get_patient(db, appt["patient_id"])
        if not patient or not patient_service.has_voicebot_consent(patient):
            raise Conflict("Patient has not consented to voice recording and AI processing")

    update: dict = {"$set": {"status": new.value}, "$push": {"status_history": _event(new, actor)}}
    if new == S.NO_SHOW:
        update["$unset"] = {"slot_key": ""}
    if new == S.COMPLETED:
        update["$set"]["completed_at"] = _now()
    result = await db.appointments.find_one_and_update(
        {"_id": appt["_id"], "status": current.value}, update, return_document=ReturnDocument.AFTER
    )
    if result is None:
        raise Conflict("The appointment was updated by someone else. Please refresh.")
    return result


async def override_visit_type(db: AsyncDatabase, appt: dict, data: VisitTypeOverrideIn, actor: dict) -> dict:
    if appt["status"] in (S.CANCELLED.value, S.NO_SHOW.value):
        raise Conflict("Cannot change a cancelled appointment")
    override = {
        "visit_type": data.visit_type.value,
        "reason": data.reason,
        "by": actor["_id"],
        "by_role": actor["role"],
        "at": _now(),
    }
    return await db.appointments.find_one_and_update(
        {"_id": appt["_id"]},
        {
            "$set": {"visit_type": data.visit_type.value, "visit_type_override": override},
            "$push": {"visit_type_override_history": override},
        },
        return_document=ReturnDocument.AFTER,
    )


async def clear_visit_type_override(db: AsyncDatabase, appt: dict) -> dict:
    return await db.appointments.find_one_and_update(
        {"_id": appt["_id"]},
        {"$set": {"visit_type": appt["visit_type_auto"], "visit_type_override": None}},
        return_document=ReturnDocument.AFTER,
    )


# --- listing -----------------------------------------------------------------


async def list_for_user(
    db: AsyncDatabase,
    user: dict,
    *,
    day: date | None,
    date_from: date | None,
    doctor_id: str | None,
    patient_id: str | None,
    status: S | None,
    limit: int,
    skip: int,
) -> list[dict]:
    query: dict = {}
    if user["role"] == "doctor":
        query["doctor_id"] = user["_id"]
    elif doctor_id:
        if not (oid := parse_object_id(doctor_id)):
            raise Invalid("Invalid doctor id")
        query["doctor_id"] = oid

    if user["role"] == "patient":
        ids = await managed_patient_ids(db, user)
        query["patient_id"] = {"$in": [patient_id] if patient_id in ids else ids}
    elif patient_id:
        query["patient_id"] = patient_id.upper()

    if day:
        query["date"] = day.isoformat()
    elif date_from:
        query["date"] = {"$gte": date_from.isoformat()}
    if status:
        query["status"] = status.value

    # Upcoming lists read best oldest-first; history lists newest-first
    order = 1 if (day or date_from) else -1
    sort = [("date", order), ("start_time", order), ("token", order)]
    return await db.appointments.find(query).sort(sort).skip(skip).limit(limit).to_list()


async def queue(db: AsyncDatabase, day: date, doctor_oid: ObjectId | None) -> list[dict]:
    query: dict = {"date": day.isoformat(), "status": {"$in": [s.value for s in QUEUE_STATUSES]}}
    if doctor_oid:
        query["doctor_id"] = doctor_oid
    return await db.appointments.find(query).sort([("doctor_name", 1), ("token", 1)]).to_list()

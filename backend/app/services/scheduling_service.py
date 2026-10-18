from datetime import date, datetime, timezone

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from app.core import clock
from app.core.config import settings
from app.core.errors import Conflict, Invalid, NotFound
from app.schemas.common import parse_object_id
from app.schemas.scheduling import DoctorScheduleIn, HolidayIn, LeaveIn

DEFAULT_PROFILE = DoctorScheduleIn().model_dump()


async def get_doctor(db: AsyncDatabase, doctor_id: str | ObjectId) -> dict:
    """Active doctor user merged with their schedule profile."""
    oid = doctor_id if isinstance(doctor_id, ObjectId) else parse_object_id(doctor_id)
    user = oid and await db.users.find_one({"_id": oid, "role": "doctor", "is_active": True})
    if not user:
        raise NotFound("Doctor not found")
    profile = await db.doctor_profiles.find_one({"_id": oid}) or {}
    return {**user, **DEFAULT_PROFILE, **{k: v for k, v in profile.items() if k != "_id"}, "has_signature": bool(profile.get("signature_file_id"))}


async def list_doctors(db: AsyncDatabase) -> list[dict]:
    users = await db.users.find({"role": "doctor", "is_active": True}).sort("full_name", 1).to_list()
    profiles = {p["_id"]: p for p in await db.doctor_profiles.find({"_id": {"$in": [u["_id"] for u in users]}}).to_list()}
    return [
        {
            **u,
            **DEFAULT_PROFILE,
            **{k: v for k, v in profiles.get(u["_id"], {}).items() if k != "_id"},
            "has_signature": bool(profiles.get(u["_id"], {}).get("signature_file_id")),
        }
        for u in users
    ]


async def save_schedule(db: AsyncDatabase, doctor_id: str, data: DoctorScheduleIn) -> dict:
    doctor = await get_doctor(db, doctor_id)
    await db.doctor_profiles.update_one({"_id": doctor["_id"]}, {"$set": data.model_dump()}, upsert=True)
    return await get_doctor(db, doctor["_id"])


# --- leave & holidays --------------------------------------------------------


async def unavailable_reason(db: AsyncDatabase, doctor_oid: ObjectId, day: date) -> str | None:
    iso = day.isoformat()
    if holiday := await db.holidays.find_one({"date": iso}):
        return f"Clinic holiday: {holiday['name']}"
    if await db.doctor_leaves.find_one({"doctor_id": doctor_oid, "start_date": {"$lte": iso}, "end_date": {"$gte": iso}}):
        return "Doctor is on leave"
    return None


async def _booked_between(db: AsyncDatabase, start: date, end: date, doctor_oid: ObjectId | None = None) -> list[dict]:
    """Appointments still holding a slot in the date range (need rescheduling if the day is blocked)."""
    query: dict = {"date": {"$gte": start.isoformat(), "$lte": end.isoformat()}, "status": "scheduled"}
    if doctor_oid:
        query["doctor_id"] = doctor_oid
    return await db.appointments.find(query).sort([("date", 1), ("start_time", 1)]).to_list()


async def list_leaves(db: AsyncDatabase, doctor_oid: ObjectId) -> list[dict]:
    since = clock.clinic_today().isoformat()
    return await db.doctor_leaves.find({"doctor_id": doctor_oid, "end_date": {"$gte": since}}).sort("start_date", 1).to_list()


async def add_leave(db: AsyncDatabase, doctor_oid: ObjectId, data: LeaveIn) -> tuple[dict, list[dict]]:
    doc = {
        "doctor_id": doctor_oid,
        "start_date": data.start_date.isoformat(),
        "end_date": data.end_date.isoformat(),
        "reason": data.reason,
        "created_at": datetime.now(timezone.utc),
    }
    await db.doctor_leaves.insert_one(doc)
    return doc, await _booked_between(db, data.start_date, data.end_date, doctor_oid)


async def delete_leave(db: AsyncDatabase, doctor_oid: ObjectId, leave_id: str) -> None:
    oid = parse_object_id(leave_id)
    result = await db.doctor_leaves.delete_one({"_id": oid, "doctor_id": doctor_oid}) if oid else None
    if not result or not result.deleted_count:
        raise NotFound("Leave not found")


async def list_holidays(db: AsyncDatabase, include_past: bool = False) -> list[dict]:
    query = {} if include_past else {"date": {"$gte": clock.clinic_today().isoformat()}}
    return await db.holidays.find(query).sort("date", 1).to_list()


async def add_holiday(db: AsyncDatabase, data: HolidayIn) -> tuple[dict, list[dict]]:
    if await db.holidays.find_one({"date": data.date.isoformat()}):
        raise Conflict("A holiday already exists on this date")
    doc = {"date": data.date.isoformat(), "name": data.name}
    await db.holidays.insert_one(doc)
    return doc, await _booked_between(db, data.date, data.date)


async def delete_holiday(db: AsyncDatabase, holiday_id: str) -> None:
    oid = parse_object_id(holiday_id)
    result = await db.holidays.delete_one({"_id": oid}) if oid else None
    if not result or not result.deleted_count:
        raise NotFound("Holiday not found")


# --- slots -------------------------------------------------------------------


def slot_times(doctor: dict, day: date) -> list[tuple[str, str]]:
    step = doctor["slot_minutes"]
    times = []
    for block in sorted(doctor["weekly"], key=lambda b: b["start"]):
        if block["weekday"] != day.weekday():
            continue
        t, end = clock.to_minutes(block["start"]), clock.to_minutes(block["end"])
        while t + step <= end:
            times.append((clock.from_minutes(t), clock.from_minutes(t + step)))
            t += step
    return times


def _is_past(day: date, start: str) -> bool:
    now = clock.clinic_now()
    return day < now.date() or (day == now.date() and clock.to_minutes(start) <= now.hour * 60 + now.minute)


async def day_slots(db: AsyncDatabase, doctor: dict, day: date) -> dict:
    result = {"doctor_id": str(doctor["_id"]), "date": day, "bookable": False, "slots": []}
    if reason := await unavailable_reason(db, doctor["_id"], day):
        return {**result, "reason": reason}
    times = slot_times(doctor, day)
    if not times:
        return {**result, "reason": "Doctor is not available on this day"}

    taken = {
        a["start_time"]
        for a in await db.appointments.find(
            {"doctor_id": doctor["_id"], "date": day.isoformat(), "slot_key": {"$exists": True}}, {"start_time": 1}
        ).to_list()
    }
    slots = [
        {"start": s, "end": e, "status": "booked" if s in taken else "past" if _is_past(day, s) else "available"}
        for s, e in times
    ]
    return {**result, "bookable": True, "slots": slots}


async def validate_slot(db: AsyncDatabase, doctor: dict, day: date, start: str) -> str:
    """Check the requested slot can be booked; returns its end time.
    (Races between two bookings are settled by the unique slot_key index.)"""
    today = clock.clinic_today()
    if day < today:
        raise Invalid("Cannot book a date in the past")
    if (day - today).days > settings.booking_horizon_days:
        raise Invalid(f"Bookings open only {settings.booking_horizon_days} days ahead")
    if reason := await unavailable_reason(db, doctor["_id"], day):
        raise Conflict(reason)
    end = dict(slot_times(doctor, day)).get(start)
    if end is None:
        raise Invalid("That time is not one of the doctor's slots")
    if _is_past(day, start):
        raise Invalid("That slot has already passed")
    return end

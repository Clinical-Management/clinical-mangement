from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.core import clock
from app.core.deps import DB, CurrentUser, require_roles
from app.core.errors import Conflict, Forbidden
from app.schemas.appointment import AppointmentStatus as S, RescheduleIn
from app.schemas.common import parse_object_id
from app.schemas.patient import Communication
from app.schemas.user import Role
from app.services import (
    appointment_service,
    notify_service,
    prescription_service,
    reminder_service as svc,
    report_service,
    scheduling_service,
)

router = APIRouter(tags=["reminders"])

Staff = Depends(require_roles(Role.ADMIN, Role.DOCTOR, Role.RECEPTIONIST))
FrontDesk = Depends(require_roles(Role.ADMIN, Role.RECEPTIONIST))
Admin = Depends(require_roles(Role.ADMIN))


class ReminderSettings(BaseModel):
    offsets_minutes: list[int] = Field(max_length=6, description="Minutes before the visit, e.g. [4320, 1440, 120]")
    nudge_after_days: int = Field(1, ge=0, le=30)
    callback_window_days: int = Field(3, ge=0, le=30)


class CallIn(BaseModel):
    outcome: Literal["no_answer", "will_book", "booked", "declined", "not_needed"]
    note: str | None = Field(None, max_length=300)


class TestReminderIn(BaseModel):
    date: date
    tests: list[str] = Field(min_length=1, max_length=20)


class CancelIn(BaseModel):
    reason: str | None = Field(None, max_length=200)


def _appt_view(a: dict) -> dict:
    return {"id": str(a["_id"]), "date": a["date"], "start_time": a.get("start_time"), "end_time": a.get("end_time"),
            "doctor_name": a["doctor_name"], "status": a["status"], "source": a["source"]}


# --- follow-up booking --------------------------------------------------------------------


@router.get("/appointments/{appointment_id}/follow-up")
async def follow_up(appointment_id: str, db: DB, user: CurrentUser):
    """The follow-up booked from this visit's prescription (if any)."""
    appt = await appointment_service.get_for_user(db, appointment_id, user)
    booked = await db.appointments.find_one({"follow_up_of": appt["_id"], "status": {"$ne": S.CANCELLED.value}}, sort=[("date", 1)])
    return {"appointment": booked and _appt_view(booked)}


@router.get("/doctors/{doctor_id}/next-free", dependencies=[Staff])
async def next_free(doctor_id: str, db: DB, on_or_after: date | None = None, count: int = Query(3, ge=1, le=10)):
    """Nearest free slots from a date (e.g. 'after 7 days'), skipping holidays, leave and full days."""
    doctor = await scheduling_service.get_doctor(db, doctor_id)
    return await svc.suggest_slots(db, doctor, on_or_after or clock.clinic_today(), count)


@router.get("/follow-ups/due", dependencies=[Staff])
async def follow_ups_due(db: DB, user: CurrentUser, doctor_id: str | None = None, days: int = Query(7, ge=1, le=31)):
    """Follow-ups booked in the coming days and advised ones that are overdue (doctors see their own)."""
    oid = user["_id"] if user["role"] == Role.DOCTOR.value else parse_object_id(doctor_id or "")
    return await svc.follow_ups_due(db, oid, days=days)


@router.get("/follow-ups/callbacks", dependencies=[FrontDesk])
async def callbacks(db: DB, include_closed: bool = False):
    """Patients to phone because an advised follow-up isn't booked."""
    return await svc.callback_list(db, include_closed)


@router.post("/follow-ups/callbacks/{appointment_id}", dependencies=[FrontDesk])
async def record_call(appointment_id: str, body: CallIn, db: DB, user: CurrentUser):
    doc = await svc.record_call(db, appointment_id, body.outcome, body.note, user)
    return {k: v for k, v in doc.items() if k not in ("_id", "appointment_id", "by")}


# --- settings and log ------------------------------------------------------------------------


@router.get("/reminders/settings", response_model=ReminderSettings, dependencies=[Staff])
async def get_settings(db: DB):
    return await svc.get_settings(db)


@router.put("/reminders/settings", response_model=ReminderSettings, dependencies=[Admin])
async def save_settings(body: ReminderSettings, db: DB):
    data = body.model_dump()
    data["offsets_minutes"] = sorted({m for m in data["offsets_minutes"] if 10 <= m <= 14 * 24 * 60}, reverse=True)
    return await svc.save_settings(db, data)


def _note(n: dict) -> dict:
    return {**{k: v for k, v in n.items() if k not in ("_id", "batch", "fallback_of", "appointment_id")},
            "id": str(n["_id"]), "appointment_id": n.get("appointment_id") and str(n["appointment_id"]),
            "ref": {k: str(v) for k, v in (n.get("ref") or {}).items()}}


@router.get("/notifications", dependencies=[FrontDesk])
async def notification_log(db: DB, patient_id: str | None = None, kind: str | None = None, status: str | None = None,
                           limit: int = Query(200, ge=1, le=500)):
    """Everything sent or scheduled, with delivery status (e.g. 'not configured' until a provider is set up)."""
    return [_note(n) for n in await notify_service.log_for(db, patient_id=patient_id, kind=kind, status=status, limit=limit)]


@router.post("/notifications/run", dependencies=[Admin])
async def run_now(db: DB):
    """Queue due reminders and send due messages now (the background worker does this every 30 seconds)."""
    await svc.queue_due(db)
    return {"sent": await notify_service.dispatch_due(db)}


@router.get("/me/notifications")
async def my_inbox(db: DB, user: CurrentUser):
    """The patient app's messages (reminders, follow-ups, medicine times)."""
    return [_note(n) for n in await notify_service.inbox(db, user)]


@router.post("/me/notifications/read", status_code=204)
async def mark_read(db: DB, user: CurrentUser):
    await notify_service.mark_read(db, user)


@router.put("/patients/{patient_id}/communication", response_model=Communication)
async def set_communication(patient_id: str, body: Communication, db: DB, user: CurrentUser):
    """Language and channels for messages; the patient or the front desk can change them."""
    if user["role"] == Role.DOCTOR.value:
        raise Forbidden("Ask the front desk or the patient to change this")
    patient = await report_service.patient_for(db, patient_id, user)
    await db.patients.update_one({"_id": patient["_id"]}, {"$set": {"communication": body.model_dump()}})
    return body


# --- medicine and test reminders from a prescription -----------------------------------------


async def _version(db, version_id: str, user: dict) -> dict:
    v = await prescription_service.get_version(db, version_id)
    await appointment_service.get_for_user(db, str(v["appointment_id"]), user)
    return v


@router.post("/prescription-versions/{version_id}/medicine-reminders")
async def medicine_reminders_on(version_id: str, db: DB, user: CurrentUser):
    v = await _version(db, version_id, user)
    return {"scheduled": await svc.schedule_medicine_reminders(db, v, user)}


@router.delete("/prescription-versions/{version_id}/medicine-reminders", status_code=204)
async def medicine_reminders_off(version_id: str, db: DB, user: CurrentUser):
    await svc.cancel_medicine_reminders(db, await _version(db, version_id, user))


@router.post("/prescription-versions/{version_id}/test-reminders")
async def test_reminder(version_id: str, body: TestReminderIn, db: DB, user: CurrentUser):
    return await svc.schedule_test_reminder(db, await _version(db, version_id, user), body.date, body.tests)


# --- public: reminder links (no login) ---------------------------------------------------------


async def _public_view(db, appt: dict) -> dict:
    clinic = await prescription_service.clinic_settings(db)
    return {**_appt_view(appt), "patient_first_name": appt["patient_name"].split()[0], "clinic_name": clinic["name"], "clinic_phone": clinic.get("phone"),
            "confirmed": bool(appt.get("confirmed_at")), "doctor_id": str(appt["doctor_id"]),
            "can_change": appt["status"] == S.SCHEDULED.value and appt["source"] != "walk_in"}


@router.get("/public/appointments/{appointment_id}")
async def public_appointment(appointment_id: str, db: DB, t: str = Query(min_length=10)):
    return await _public_view(db, await svc.appointment_for_link(db, appointment_id, t))


@router.post("/public/appointments/{appointment_id}/confirm")
async def public_confirm(appointment_id: str, db: DB, t: str = Query(min_length=10)):
    appt = await svc.appointment_for_link(db, appointment_id, t)
    if appt["status"] != S.SCHEDULED.value:
        raise Conflict("This appointment can no longer be confirmed")
    await db.appointments.update_one({"_id": appt["_id"]}, {"$set": {"confirmed_at": svc._now()}})
    return await _public_view(db, await db.appointments.find_one({"_id": appt["_id"]}))


@router.post("/public/appointments/{appointment_id}/cancel")
async def public_cancel(appointment_id: str, body: CancelIn, db: DB, t: str = Query(min_length=10)):
    appt = await svc.appointment_for_link(db, appointment_id, t)
    return await _public_view(db, await appointment_service.cancel(db, appt, body.reason or "Cancelled from reminder", svc.PATIENT_LINK))


@router.get("/public/appointments/{appointment_id}/slots")
async def public_slots(appointment_id: str, db: DB, day: date = Query(alias="date"), t: str = Query(min_length=10)):
    appt = await svc.appointment_for_link(db, appointment_id, t)
    doctor = await scheduling_service.get_doctor(db, appt["doctor_id"])
    return await scheduling_service.day_slots(db, doctor, day)


@router.post("/public/appointments/{appointment_id}/reschedule")
async def public_reschedule(appointment_id: str, body: RescheduleIn, db: DB, t: str = Query(min_length=10)):
    appt = await svc.appointment_for_link(db, appointment_id, t)
    moved = await appointment_service.reschedule(db, appt, body, svc.PATIENT_LINK)
    await db.appointments.update_one({"_id": moved["_id"]}, {"$set": {"confirmed_at": svc._now()}, "$unset": {"reminders_sent": ""}})
    return await _public_view(db, await db.appointments.find_one({"_id": moved["_id"]}))

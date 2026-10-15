from datetime import date

from fastapi import APIRouter, Depends, Query, status

from app.core import clock
from app.core.deps import DB, CurrentUser, require_roles
from app.core.errors import Forbidden, Invalid
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentOut,
    AppointmentStatus,
    CancelIn,
    PaymentUpdate,
    RescheduleIn,
    StatusUpdate,
    VisitTypeOverrideIn,
    VisitTypePreview,
    WalkInCreate,
)
from app.schemas.common import parse_object_id
from app.schemas.user import Role
from app.services import appointment_service as svc
from app.services import scheduling_service as sched

router = APIRouter(prefix="/appointments", tags=["appointments"])

FrontDesk = Depends(require_roles(Role.ADMIN, Role.RECEPTIONIST))
Staff = Depends(require_roles(Role.ADMIN, Role.RECEPTIONIST, Role.DOCTOR))


@router.get("", response_model=list[AppointmentOut])
async def list_appointments(
    db: DB,
    user: CurrentUser,
    date: date | None = Query(None, description="Exact day"),
    date_from: date | None = Query(None, description="This day onwards (ignored when `date` is set)"),
    doctor_id: str | None = None,
    patient_id: str | None = None,
    status: AppointmentStatus | None = None,
    limit: int = Query(100, ge=1, le=500),
    skip: int = Query(0, ge=0),
):
    """Front desk: all. Doctors: their own. Patients: their family profiles'."""
    return await svc.list_for_user(
        db, user, day=date, date_from=date_from, doctor_id=doctor_id, patient_id=patient_id,
        status=status, limit=limit, skip=skip,
    )


@router.post(
    "",
    response_model=AppointmentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(Role.ADMIN, Role.RECEPTIONIST, Role.PATIENT))],
)
async def book_appointment(body: AppointmentCreate, db: DB, user: CurrentUser):
    """Online (patient) or front-desk booking into a free slot."""
    return await svc.book(db, body, user)


@router.post("/walk-in", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED, dependencies=[FrontDesk])
async def register_walk_in(body: WalkInCreate, db: DB, user: CurrentUser):
    """Adds the patient to today's queue with a token, without a slot."""
    return await svc.walk_in(db, body, user)


@router.get("/queue", response_model=list[AppointmentOut], dependencies=[Staff])
async def get_queue(db: DB, user: CurrentUser, date: date | None = None, doctor_id: str | None = None):
    """Checked-in patients for a day (default today), ordered by token. Doctors see only their own."""
    if user["role"] == Role.DOCTOR.value:
        doctor_oid = user["_id"]
    elif doctor_id:
        if not (doctor_oid := parse_object_id(doctor_id)):
            raise Invalid("Invalid doctor id")
    else:
        doctor_oid = None
    return await svc.queue(db, date or clock.clinic_today(), doctor_oid)


@router.get("/visit-type-preview", response_model=VisitTypePreview, dependencies=[FrontDesk])
async def preview_visit_type(patient_id: str, doctor_id: str, date: date, db: DB):
    doctor = await sched.get_doctor(db, doctor_id)
    return await svc.compute_visit_type(db, patient_id.upper(), doctor, date)


@router.get("/{appointment_id}", response_model=AppointmentOut)
async def get_appointment(appointment_id: str, db: DB, user: CurrentUser):
    return await svc.get_for_user(db, appointment_id, user)


@router.post("/{appointment_id}/check-in", response_model=AppointmentOut, dependencies=[FrontDesk])
async def check_in(appointment_id: str, db: DB, user: CurrentUser):
    return await svc.check_in(db, await svc.get_for_user(db, appointment_id, user), user)


@router.post("/{appointment_id}/reschedule", response_model=AppointmentOut)
async def reschedule(appointment_id: str, body: RescheduleIn, db: DB, user: CurrentUser):
    if user["role"] == Role.DOCTOR.value:
        raise Forbidden("Please ask the front desk to reschedule")
    return await svc.reschedule(db, await svc.get_for_user(db, appointment_id, user), body, user)


@router.post("/{appointment_id}/cancel", response_model=AppointmentOut)
async def cancel(appointment_id: str, body: CancelIn, db: DB, user: CurrentUser):
    if user["role"] == Role.DOCTOR.value:
        raise Forbidden("Please ask the front desk to cancel")
    return await svc.cancel(db, await svc.get_for_user(db, appointment_id, user), body.reason, user)


@router.post("/{appointment_id}/status", response_model=AppointmentOut, dependencies=[Staff])
async def update_status(appointment_id: str, body: StatusUpdate, db: DB, user: CurrentUser):
    """Move a patient along the queue (e.g. waiting -> with_voicebot -> in_consultation -> completed)."""
    return await svc.set_status(db, await svc.get_for_user(db, appointment_id, user), body.status, user)


@router.put("/{appointment_id}/visit-type", response_model=AppointmentOut, dependencies=[FrontDesk])
async def override_visit_type(appointment_id: str, body: VisitTypeOverrideIn, db: DB, user: CurrentUser):
    """Override the auto-detected visit type. A reason is mandatory and kept in the history."""
    return await svc.override_visit_type(db, await svc.get_for_user(db, appointment_id, user), body, user)


@router.delete("/{appointment_id}/visit-type", response_model=AppointmentOut, dependencies=[FrontDesk])
async def clear_visit_type_override(appointment_id: str, db: DB, user: CurrentUser):
    """Go back to the auto-detected visit type."""
    return await svc.clear_visit_type_override(db, await svc.get_for_user(db, appointment_id, user))


@router.put("/{appointment_id}/payment", response_model=AppointmentOut, dependencies=[FrontDesk])
async def update_payment(appointment_id: str, body: PaymentUpdate, db: DB, user: CurrentUser):
    """Paid visits anchor the follow-up window (until a billing module replaces this)."""
    return await svc.set_payment(db, await svc.get_for_user(db, appointment_id, user), body.payment_status)

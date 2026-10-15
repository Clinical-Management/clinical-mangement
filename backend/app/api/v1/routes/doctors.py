from datetime import date

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.core.deps import DB, CurrentUser, require_roles
from app.core.errors import Forbidden
from app.schemas.appointment import AppointmentOut
from app.schemas.scheduling import DaySlots, DoctorOut, DoctorScheduleIn, LeaveIn, LeaveOut
from app.schemas.user import Role
from app.services import scheduling_service as sched

router = APIRouter(prefix="/doctors", tags=["doctors"])

Staff = Depends(require_roles(Role.ADMIN, Role.RECEPTIONIST, Role.DOCTOR))


class LeaveCreated(BaseModel):
    leave: LeaveOut
    # Booked appointments inside the leave: the front desk should reschedule these
    conflicting_appointments: list[AppointmentOut]


def _ensure_admin_or_self(user: dict, doctor_id: str) -> None:
    if user["role"] != Role.ADMIN.value and str(user["_id"]) != doctor_id:
        raise Forbidden("Only an admin or the doctor can change this")


@router.get("", response_model=list[DoctorOut])
async def list_doctors(db: DB, _: CurrentUser):
    return await sched.list_doctors(db)


@router.get("/{doctor_id}", response_model=DoctorOut)
async def get_doctor(doctor_id: str, db: DB, _: CurrentUser):
    return await sched.get_doctor(db, doctor_id)


@router.put("/{doctor_id}/schedule", response_model=DoctorOut, dependencies=[Depends(require_roles(Role.ADMIN))])
async def save_schedule(doctor_id: str, body: DoctorScheduleIn, db: DB):
    """Weekly working hours, slot length and follow-up window."""
    return await sched.save_schedule(db, doctor_id, body)


@router.get("/{doctor_id}/slots", response_model=DaySlots)
async def get_slots(doctor_id: str, db: DB, _: CurrentUser, date: date):
    return await sched.day_slots(db, await sched.get_doctor(db, doctor_id), date)


@router.get("/{doctor_id}/leaves", response_model=list[LeaveOut], dependencies=[Staff])
async def list_leaves(doctor_id: str, db: DB):
    return await sched.list_leaves(db, (await sched.get_doctor(db, doctor_id))["_id"])


@router.post("/{doctor_id}/leaves", response_model=LeaveCreated, status_code=status.HTTP_201_CREATED)
async def add_leave(doctor_id: str, body: LeaveIn, db: DB, user: CurrentUser):
    _ensure_admin_or_self(user, doctor_id)
    doctor = await sched.get_doctor(db, doctor_id)
    leave, conflicts = await sched.add_leave(db, doctor["_id"], body)
    return {"leave": leave, "conflicting_appointments": conflicts}


@router.delete("/{doctor_id}/leaves/{leave_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_leave(doctor_id: str, leave_id: str, db: DB, user: CurrentUser):
    _ensure_admin_or_self(user, doctor_id)
    await sched.delete_leave(db, (await sched.get_doctor(db, doctor_id))["_id"], leave_id)

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.core.deps import DB, CurrentUser, require_roles
from app.schemas.appointment import AppointmentOut
from app.schemas.scheduling import HolidayIn, HolidayOut
from app.schemas.user import Role
from app.services import scheduling_service as sched

router = APIRouter(prefix="/holidays", tags=["holidays"])

AdminOnly = Depends(require_roles(Role.ADMIN))


class HolidayCreated(BaseModel):
    holiday: HolidayOut
    # Booked appointments on that day across all doctors: these need rescheduling
    conflicting_appointments: list[AppointmentOut]


@router.get("", response_model=list[HolidayOut])
async def list_holidays(db: DB, _: CurrentUser, include_past: bool = False):
    return await sched.list_holidays(db, include_past)


@router.post("", response_model=HolidayCreated, status_code=status.HTTP_201_CREATED, dependencies=[AdminOnly])
async def add_holiday(body: HolidayIn, db: DB):
    holiday, conflicts = await sched.add_holiday(db, body)
    return {"holiday": holiday, "conflicting_appointments": conflicts}


@router.delete("/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[AdminOnly])
async def delete_holiday(holiday_id: str, db: DB):
    await sched.delete_holiday(db, holiday_id)

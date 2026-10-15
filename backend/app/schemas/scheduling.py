from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.clock import to_minutes
from app.schemas.common import PyObjectId

HHMM = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$", examples=["09:30"])]


class WorkingBlock(BaseModel):
    weekday: int = Field(ge=0, le=6, description="0 = Monday ... 6 = Sunday")
    start: HHMM
    end: HHMM

    @model_validator(mode="after")
    def start_before_end(self):
        if to_minutes(self.start) >= to_minutes(self.end):
            raise ValueError("Block start must be before its end")
        return self


class DoctorScheduleIn(BaseModel):
    specialization: str | None = Field(None, max_length=120)
    slot_minutes: int = Field(15, ge=5, le=120)
    follow_up_days: int = Field(7, ge=0, le=365, description="Follow-up window after the last paid visit")
    weekly: list[WorkingBlock] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def no_overlaps(self):
        blocks = sorted(self.weekly, key=lambda b: (b.weekday, to_minutes(b.start)))
        for a, b in zip(blocks, blocks[1:]):
            if a.weekday == b.weekday and to_minutes(b.start) < to_minutes(a.end):
                raise ValueError(f"Overlapping working hours on weekday {a.weekday}")
        return self


class DoctorOut(DoctorScheduleIn):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(validation_alias="_id")
    full_name: str
    email: str


class LeaveIn(BaseModel):
    start_date: date
    end_date: date
    reason: str | None = Field(None, max_length=200)

    @model_validator(mode="after")
    def ordered(self):
        if self.end_date < self.start_date:
            raise ValueError("End date must be on or after start date")
        return self


class LeaveOut(LeaveIn):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(validation_alias="_id")
    doctor_id: PyObjectId
    created_at: datetime


class HolidayIn(BaseModel):
    date: date
    name: str = Field(min_length=1, max_length=120)


class HolidayOut(HolidayIn):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(validation_alias="_id")


class Slot(BaseModel):
    start: str
    end: str
    status: Literal["available", "booked", "past"]


class DaySlots(BaseModel):
    doctor_id: str
    date: date
    bookable: bool
    reason: str | None = None
    slots: list[Slot] = []

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import PyObjectId
from app.schemas.scheduling import HHMM


class VisitType(str, Enum):
    NEW = "new"
    FOLLOW_UP = "follow_up"
    RETURNING = "returning"


class AppointmentStatus(str, Enum):
    SCHEDULED = "scheduled"  # booked, patient not yet arrived
    WAITING = "waiting"  # checked in, has a token
    WITH_VOICEBOT = "with_voicebot"
    IN_CONSULTATION = "in_consultation"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class Source(str, Enum):
    ONLINE = "online"
    FRONT_DESK = "front_desk"
    WALK_IN = "walk_in"


class PaymentStatus(str, Enum):
    UNPAID = "unpaid"
    PAID = "paid"
    WAIVED = "waived"


class AppointmentCreate(BaseModel):
    patient_id: str
    doctor_id: str
    date: date
    start_time: HHMM


class WalkInCreate(BaseModel):
    patient_id: str
    doctor_id: str


class RescheduleIn(BaseModel):
    date: date
    start_time: HHMM


class CancelIn(BaseModel):
    reason: str | None = Field(None, max_length=300)


class StatusUpdate(BaseModel):
    status: AppointmentStatus


class VisitTypeOverrideIn(BaseModel):
    visit_type: VisitType
    reason: str = Field(max_length=300)

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("A reason is required to override the visit type")
        return v


class PaymentUpdate(BaseModel):
    payment_status: PaymentStatus


class VisitTypeOverrideOut(BaseModel):
    visit_type: VisitType
    reason: str
    by_role: str
    at: datetime


class StatusEvent(BaseModel):
    status: AppointmentStatus
    at: datetime
    by_role: str


class RescheduleEvent(BaseModel):
    from_date: date
    from_time: str | None
    to_date: date
    to_time: str
    at: datetime
    by_role: str


class AppointmentOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(validation_alias="_id")
    patient_id: str
    patient_name: str
    doctor_id: PyObjectId
    doctor_name: str
    date: date
    start_time: str | None
    end_time: str | None
    source: Source
    status: AppointmentStatus
    token: int | None
    checked_in_at: datetime | None
    visit_type: VisitType
    visit_type_auto: VisitType
    visit_type_override: VisitTypeOverrideOut | None
    payment_status: PaymentStatus
    cancel_reason: str | None = None
    # Pre-visit history (voicebot); red_flag marks urgent symptoms raised there
    history_session_id: PyObjectId | None = None
    history_status: str | None = None
    red_flag: bool = False
    red_flag_labels: str | None = None
    vitals_flag: str | None = None  # latest vitals: normal | abnormal | critical
    status_history: list[StatusEvent]
    reschedule_history: list[RescheduleEvent]
    created_at: datetime


class VisitTypePreview(BaseModel):
    visit_type: VisitType
    last_visit_date: date | None
    last_paid_visit_date: date | None
    follow_up_days: int

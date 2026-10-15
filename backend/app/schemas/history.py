from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import PyObjectId

Language = Literal["en", "hi", "mr"]
Mode = Literal["voice", "text", "manual"]


class SessionCreate(BaseModel):
    appointment_id: str
    mode: Mode
    # patient_device: the patient's own phone; clinic_device: tablet/kiosk; staff: manual entry
    channel: Literal["patient_device", "clinic_device", "staff"]
    language: Language | Literal["auto"] = "auto"


class PatientMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    input: Literal["voice", "text"] = "text"


class LanguageIn(BaseModel):
    language: Language | Literal["auto"]


class ManualFieldsIn(BaseModel):
    fields: dict[str, str]


class FieldReviewIn(BaseModel):
    action: Literal["accept", "reject", "edit"]
    value: str | None = Field(None, max_length=4000)


class SummaryIn(BaseModel):
    summary: str = Field(min_length=1, max_length=8000)


class TranscriptEntry(BaseModel):
    role: Literal["assistant", "patient", "staff"]
    text: str
    language: str
    input: str | None = None
    at: datetime


class PatientSessionView(BaseModel):
    """What the patient (or kiosk) sees: the conversation and the read-back summary only."""

    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(validation_alias="_id")
    status: Literal["in_progress", "review", "submitted", "escalated"]
    mode: Mode
    language: Language
    language_mode: Literal["auto", "manual"]
    patient_first_name: str
    doctor_name: str
    transcript: list[TranscriptEntry]
    patient_summary: str | None


class LinkOut(BaseModel):
    token: str
    path: str
    expires_at: datetime


class SessionStarted(BaseModel):
    session: PatientSessionView
    link: LinkOut | None


class FieldOut(BaseModel):
    key: str
    label: str
    section: str
    value: str
    origin: str | None
    review_status: str | None


class RedFlagOut(BaseModel):
    code: str
    label: str
    source: Literal["rules", "model"]
    evidence: str
    at: datetime


class EditLogEntry(BaseModel):
    field: str
    action: str
    old: str | None
    new: str | None
    by_role: str
    at: datetime


class SessionOut(BaseModel):
    """Clinical view for the doctor / admin."""

    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(validation_alias="_id")
    appointment_id: PyObjectId
    patient_id: str
    patient_name: str
    doctor_name: str
    status: str
    mode: Mode
    channel: str
    language: Language
    template: str
    returning: bool
    fields: list[FieldOut]
    summary: str | None
    summary_source: str | None
    patient_summary: str | None
    red_flags: list[RedFlagOut]
    edit_log: list[EditLogEntry]
    transcript: list[TranscriptEntry]
    created_at: datetime
    submitted_at: datetime | None


class AlertOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(validation_alias="_id")
    type: str
    message: str
    patient_id: str
    patient_name: str
    doctor_name: str
    appointment_id: PyObjectId
    session_id: PyObjectId | None
    codes: list[str]
    created_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by_role: str | None

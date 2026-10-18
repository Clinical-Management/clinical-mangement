from datetime import date, datetime

from pydantic import BaseModel, Field


class DiffOp(BaseModel):
    op: str  # equal | insert | delete
    text: str


class Suggestion(BaseModel):
    text: str
    diff: list[DiffOp]


class SectionOut(BaseModel):
    key: str
    title: str
    text: str
    edited: bool
    suggestion: Suggestion | None  # new wording for a section the doctor edited
    last_change: list[DiffOp] | None  # what the last regeneration changed in this section


class CaseSummaryOut(BaseModel):
    appointment_id: str
    status: str  # draft | final
    sections: list[SectionOut]
    stale: bool  # sources changed since it was generated
    pending_changes: list[str]
    last_regeneration_changes: list[str]
    generated_by: str  # ai | rules
    generation_note: str | None
    generated_at: datetime
    finalized_at: datetime | None
    finalized_by_role: str | None
    version: int
    updated_at: datetime


class SectionsEdit(BaseModel):
    sections: dict[str, str] = Field(max_length=6)


class PrintSection(BaseModel):
    key: str
    title: str
    text: str


class PrintOut(BaseModel):
    """Everything the printable prescription needs."""

    clinic_name: str
    doctor_name: str
    doctor_specialization: str | None
    patient_name: str
    patient_id: str
    patient_age: int | None
    patient_gender: str
    allergies: list[str]
    visit_date: date
    token: int | None
    case_summary: list[PrintSection]
    case_summary_status: str | None  # draft | final | None (none yet)
    prescription: dict

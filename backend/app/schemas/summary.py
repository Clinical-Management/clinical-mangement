from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import PyObjectId


class TestRowOut(BaseModel):
    id: str
    name: str
    value: str | None
    unit: str | None
    reference_range: str | None
    printed_flag: str | None
    page: int | None
    bbox: list[int] | None  # [x0, y0, x1, y1] on 0-1000 scale of the page image
    source_text: str | None
    confidence: str | None  # AI confidence: high | medium | low (None for doctor-added rows)
    analyte_key: str
    value_numeric: float | None
    ref_low: float | None
    ref_high: float | None
    flag: str | None  # normal | low | high | critical_low | critical_high | abnormal
    critical: bool
    edited: bool
    added_by_doctor: bool


class EditLogOut(BaseModel):
    field: str
    action: str
    changes: dict
    by_role: str
    at: datetime


class SummaryOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(validation_alias="_id")
    report_id: PyObjectId
    report_version: int
    patient_id: str
    report_type: str
    report_date: date
    status: str  # processing | ready | approved | failed | no_consent
    error: str | None
    document_kind: str | None
    readability: str | None
    lab_name: str | None
    tests: list[TestRowOut]
    summary_text: str | None
    findings: str | None
    impression: str | None
    image_observation: str | None
    overall_confidence: str | None
    critical_values: list[str]
    page_count: int
    ai_generated: bool
    label: str
    edit_log: list[EditLogOut]
    approved_at: datetime | None
    approved_by_role: str | None
    updated_at: datetime


class PatientTestOut(BaseModel):
    name: str
    value: str | None
    unit: str | None
    reference_range: str | None
    flag: str | None


class PatientSummaryOut(BaseModel):
    """Approved summaries only - what patients may see."""

    report_id: PyObjectId
    report_type: str
    report_date: date
    summary_text: str | None
    impression: str | None
    tests: list[PatientTestOut]
    approved_at: datetime
    label: str


class TestEdit(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    value: str | None = Field(None, max_length=60)
    unit: str | None = Field(None, max_length=40)
    reference_range: str | None = Field(None, max_length=80)


class TestAdd(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=60)
    unit: str | None = Field(None, max_length=40)
    reference_range: str | None = Field(None, max_length=80)


class TextEdit(BaseModel):
    summary_text: str | None = Field(None, max_length=4000)
    findings: str | None = Field(None, max_length=8000)
    impression: str | None = Field(None, max_length=4000)
    image_observation: str | None = Field(None, max_length=4000)


class TrendPoint(BaseModel):
    date: date
    value: float
    unit: str | None
    flag: str | None
    report_id: str
    approved: bool
    current: bool

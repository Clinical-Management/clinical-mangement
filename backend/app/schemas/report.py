from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import PyObjectId


class ReportType(str, Enum):
    BLOOD_TEST = "blood_test"
    XRAY = "xray"
    CT = "ct"
    MRI = "mri"
    ECG = "ecg"
    ULTRASOUND = "ultrasound"
    PATHOLOGY = "pathology"
    OTHER = "other"


REPORT_TYPE_LABELS = {
    "blood_test": "Blood test",
    "xray": "X-ray",
    "ct": "CT",
    "mri": "MRI",
    "ecg": "ECG",
    "ultrasound": "Ultrasound",
    "pathology": "Pathology",
    "other": "Other",
}


class FileCheckOut(BaseModel):
    ok: bool
    kind: str | None
    errors: list[str]
    warnings: list[str]
    info: dict
    duplicate_of: str | None = None  # report id if the same file is already in the patient's library


class ReportVersionOut(BaseModel):
    version: int
    filename: str
    content_type: str
    kind: str
    size_bytes: int
    has_processed: bool  # enhanced copy of a camera capture
    source: str  # upload | camera
    warnings: list[str]
    info: dict
    reason: str | None
    uploaded_at: datetime
    uploaded_by_role: str


class SummaryBrief(BaseModel):
    id: str
    status: str
    critical_values: list[str]
    abnormal_count: int


class ReportOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(validation_alias="_id")
    patient_id: str
    patient_name: str
    appointment_id: PyObjectId | None
    visit_date: date | None
    report_type: ReportType
    report_date: date
    ordering_doctor: str
    title: str | None
    notes: str | None
    current_version: int
    versions: list[ReportVersionOut]
    created_at: datetime
    updated_at: datetime
    summary: SummaryBrief | None = None  # with ?include_summary=true


class ReportUpdate(BaseModel):
    report_type: ReportType | None = None
    report_date: date | None = None
    ordering_doctor: str | None = Field(None, min_length=1, max_length=120)
    appointment_id: str | None = None
    title: str | None = Field(None, max_length=120)
    notes: str | None = Field(None, max_length=1000)


class ExportIn(BaseModel):
    report_ids: list[str] = Field(min_length=1, max_length=50)

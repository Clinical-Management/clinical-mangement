import datetime as dt
from datetime import datetime

from pydantic import BaseModel, Field


class Medicine(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    dose: str | None = Field(None, max_length=60)  # e.g. "500 mg"
    frequency: str | None = Field(None, max_length=60)  # e.g. "1-0-1", "twice daily"
    duration: str | None = Field(None, max_length=60)  # e.g. "5 days"
    route: str | None = Field(None, max_length=40)  # oral, topical, ...
    instructions: str | None = Field(None, max_length=200)  # e.g. "after food"


class Investigation(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    notes: str | None = Field(None, max_length=200)


class FollowUp(BaseModel):
    in_days: int | None = Field(None, ge=0, le=365)
    date: dt.date | None = None
    note: str | None = Field(None, max_length=300)


class PrescriptionIn(BaseModel):
    medicines: list[Medicine] = Field(default_factory=list, max_length=50)
    investigations: list[Investigation] = Field(default_factory=list, max_length=50)
    advice: str = Field("", max_length=4000)
    follow_up: FollowUp | None = None


class AllergyWarning(BaseModel):
    medicine: str
    allergy: str
    reason: str


class PrescriptionOut(PrescriptionIn):
    appointment_id: str
    patient_id: str
    allergy_warnings: list[AllergyWarning]
    updated_at: datetime | None
    updated_by_role: str | None

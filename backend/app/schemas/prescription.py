import datetime as dt
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import PyObjectId


class Medicine(BaseModel):
    name: str = Field(min_length=1, max_length=120)  # as printed, e.g. "Dolo 650" or "Paracetamol"
    medicine_id: str | None = Field(None, max_length=40)  # medicine master entry, when picked from search
    generic: str | None = Field(None, max_length=120)
    brand: str | None = Field(None, max_length=120)
    dose: str | None = Field(None, max_length=60)  # e.g. "500 mg"
    frequency: str | None = Field(None, max_length=60)  # e.g. "1-0-1", "TDS", "SOS"
    duration: str | None = Field(None, max_length=60)  # e.g. "5 days"
    route: str | None = Field(None, max_length=40)  # oral, topical, inhaled...
    instructions: str | None = Field(None, max_length=200)  # e.g. "after food"


class Investigation(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    notes: str | None = Field(None, max_length=200)


class FollowUp(BaseModel):
    in_days: int | None = Field(None, ge=0, le=365)
    date: dt.date | None = None
    note: str | None = Field(None, max_length=300)


class Referral(BaseModel):
    to: str = Field(min_length=1, max_length=120)  # doctor / hospital
    specialty: str | None = Field(None, max_length=80)
    notes: str | None = Field(None, max_length=1000)


class PrescriptionIn(BaseModel):
    medicines: list[Medicine] = Field(default_factory=list, max_length=50)
    investigations: list[Investigation] = Field(default_factory=list, max_length=50)
    advice: str = Field("", max_length=4000)
    diet_lifestyle: str = Field("", max_length=4000)
    referral: Referral | None = None
    follow_up: FollowUp | None = None
    # which finalized case-summary sections to print in the prescription (missing = default)
    summary_sections: dict[str, bool] = Field(default_factory=dict)


class Check(BaseModel):
    type: Literal["allergy", "interaction", "duplicate", "dose"]
    severity: Literal["high", "moderate", "info"]
    medicines: list[str]
    message: str


class PrescriptionOut(PrescriptionIn):
    appointment_id: str
    patient_id: str
    status: Literal["draft", "final"]
    current_version: int  # last finalized version (0 = none yet)
    editing_version: int  # the version these edits will become
    checks: list[Check]
    updated_at: datetime | None
    updated_by_role: str | None


class FinalizeIn(BaseModel):
    acknowledged: bool = False  # the doctor has seen the warnings
    override_reason: str | None = Field(None, max_length=300)  # required to finalize past high-severity warnings


class VersionOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(validation_alias="_id")
    appointment_id: PyObjectId
    version: int
    public_id: str
    content: PrescriptionIn
    case_summary: list[dict]
    checks: list[Check]
    override_reason: str | None
    finalized_at: datetime
    finalized_by_role: str
    superseded: bool
    letterhead: dict
    medicine_reminders: dict | None = None  # {"on": bool, "count": int} when the patient opted in


class DeliveryIn(BaseModel):
    channel: Literal["print", "whatsapp", "sms", "email", "patient_app"]
    to: str | None = Field(None, max_length=120)  # phone or email; defaults to the patient's
    language: Literal["en", "hi", "mr"] = "en"


class DeliveryOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(validation_alias="_id")
    channel: str
    to: str | None
    language: str
    status: Literal["sent", "link_ready", "published", "recorded", "failed"]
    detail: str | None
    link: str | None  # secure patient link (expires)
    share_url: str | None  # wa.me / sms: / mailto: to open on this device
    at: datetime
    by_role: str


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    medicines: list[Medicine] = Field(default_factory=list, max_length=50)
    investigations: list[Investigation] = Field(default_factory=list, max_length=50)
    advice: str = Field("", max_length=4000)
    diet_lifestyle: str = Field("", max_length=4000)


class TemplateOut(TemplateIn):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(validation_alias="_id")
    created_at: datetime


class FavouriteIn(BaseModel):
    medicine: Medicine


class FavouriteOut(FavouriteIn):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(validation_alias="_id")


class MedicineEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    generic: str = Field(min_length=1, max_length=120)
    brands: list[str] = Field(default_factory=list, max_length=30)
    drug_class: str = Field("other", alias="class", max_length=40)
    forms: list[str] = Field(default_factory=list, max_length=30)
    routes: list[str] = Field(default_factory=list, max_length=10)
    defaults: dict = Field(default_factory=dict)
    adult: dict | None = None  # {max_single_mg, max_daily_mg}
    child: dict | None = None  # {max_mg_per_kg_dose, max_mg_per_kg_day, max_daily_mg}


class MedicineOut(MedicineEntry):
    id: PyObjectId = Field(validation_alias="_id")
    class_label: str
    matched_brand: str | None = None
    source: str
    active: bool

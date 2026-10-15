import re
from datetime import date, datetime
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field, field_validator, model_validator

from app.schemas.common import PyObjectId


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    UNDISCLOSED = "prefer_not_to_say"


class BloodGroup(str, Enum):
    A_POS = "A+"
    A_NEG = "A-"
    B_POS = "B+"
    B_NEG = "B-"
    AB_POS = "AB+"
    AB_NEG = "AB-"
    O_POS = "O+"
    O_NEG = "O-"
    UNKNOWN = "unknown"


class Relationship(str, Enum):
    """How a profile relates to the account holder that manages it."""

    SELF = "self"
    SPOUSE = "spouse"
    CHILD = "child"
    PARENT = "parent"
    SIBLING = "sibling"
    OTHER = "other"


class Severity(str, Enum):
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


def _validate_phone(value: str) -> str:
    value = value.strip()
    if not re.fullmatch(r"\+?[\d\s\-()]+", value):
        raise ValueError("Phone may only contain digits, spaces, dashes, brackets and a leading +")
    if not 7 <= len(re.sub(r"\D", "", value)) <= 15:
        raise ValueError("Phone must have 7 to 15 digits")
    return value


Phone = Annotated[str, AfterValidator(_validate_phone)]
ShortText = Annotated[str, Field(min_length=1, max_length=120)]


class Address(BaseModel):
    line1: str = Field(min_length=1, max_length=200)
    line2: str | None = Field(None, max_length=200)
    city: ShortText
    state: str | None = Field(None, max_length=120)
    postal_code: str | None = Field(None, max_length=20)
    country: str | None = Field(None, max_length=120)


class EmergencyContact(BaseModel):
    name: ShortText
    relationship: ShortText
    phone: Phone


class Allergy(BaseModel):
    substance: ShortText
    reaction: str | None = Field(None, max_length=200)
    severity: Severity | None = None


class ChronicCondition(BaseModel):
    name: ShortText
    since_year: int | None = Field(None, ge=1900, le=2100)
    notes: str | None = Field(None, max_length=500)


class Medication(BaseModel):
    name: ShortText
    dosage: str | None = Field(None, max_length=120)
    frequency: str | None = Field(None, max_length=120)
    notes: str | None = Field(None, max_length=500)


class MedicalInfo(BaseModel):
    allergies: list[Allergy] = Field(default_factory=list, max_length=100)
    chronic_conditions: list[ChronicCondition] = Field(default_factory=list, max_length=100)
    current_medications: list[Medication] = Field(default_factory=list, max_length=100)


class ConsentIn(BaseModel):
    data_storage: bool
    voice_recording: bool = False
    ai_processing: bool = False

    @field_validator("data_storage")
    @classmethod
    def data_storage_required(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Consent to data storage is required to keep a patient record")
        return v


class PatientDemographics(BaseModel):
    full_name: ShortText
    date_of_birth: date | None = None
    age: int | None = Field(None, ge=0, le=130, description="Used only when date of birth is unknown")
    gender: Gender
    phone: Phone
    email: EmailStr | None = None
    address: Address | None = None
    emergency_contact: EmergencyContact | None = None
    blood_group: BloodGroup = BloodGroup.UNKNOWN
    relationship: Relationship | None = None

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return " ".join(v.split())

    @model_validator(mode="after")
    def dob_or_age(self):
        if self.date_of_birth is None and self.age is None:
            raise ValueError("Provide either date of birth or age")
        if self.date_of_birth and self.date_of_birth > date.today():
            raise ValueError("Date of birth cannot be in the future")
        return self


class PatientCreate(PatientDemographics):
    consent: ConsentIn
    # Set after the user has reviewed the duplicate warning and confirmed this is a different person
    allow_duplicate: bool = False


class ConsentOut(BaseModel):
    data_storage: bool
    voice_recording: bool
    ai_processing: bool
    updated_at: datetime
    updated_by_role: str


class PatientOut(BaseModel):
    patient_id: str
    full_name: str
    date_of_birth: date | None
    age: int | None
    gender: Gender
    phone: str
    email: str | None
    address: Address | None
    emergency_contact: EmergencyContact | None
    blood_group: BloodGroup
    relationship: Relationship | None
    managed_by: PyObjectId | None
    consent: ConsentOut
    voicebot_allowed: bool
    medical: MedicalInfo | None  # hidden from receptionists
    medical_updated_at: datetime | None = None
    medical_updated_by_role: str | None = None
    possible_duplicates: list[str] = []
    created_at: datetime


class DuplicateMatch(BaseModel):
    patient_id: str
    full_name: str
    date_of_birth: date | None
    age: int | None
    phone: str
    matched_on: list[str]

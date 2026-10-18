from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.clinical.vitals import PLAUSIBLE
from app.schemas.common import PyObjectId


def _check_range(key: str, value: float | None) -> None:
    lo, hi = PLAUSIBLE[key]
    if value is not None and not lo <= value <= hi:
        raise ValueError(f"{key.replace('_', ' ')} must be between {lo:g} and {hi:g}; please re-check the reading")


class VitalsIn(BaseModel):
    bp_systolic: int | None = None
    bp_diastolic: int | None = None
    pulse: int | None = None
    temperature: float | None = None
    temperature_unit: Literal["C", "F"] = "C"
    spo2: int | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    note: str | None = Field(None, max_length=500)

    @property
    def temperature_c(self) -> float | None:
        if self.temperature is None:
            return None
        c = (self.temperature - 32) * 5 / 9 if self.temperature_unit == "F" else self.temperature
        return round(c, 1)

    @model_validator(mode="after")
    def validate_readings(self):
        values = {
            "bp_systolic": self.bp_systolic,
            "bp_diastolic": self.bp_diastolic,
            "pulse": self.pulse,
            "temperature_c": self.temperature_c,
            "spo2": self.spo2,
            "weight_kg": self.weight_kg,
            "height_cm": self.height_cm,
        }
        if all(v is None for v in values.values()):
            raise ValueError("Enter at least one reading")
        for key, value in values.items():
            _check_range(key, value)
        if (self.bp_systolic is None) != (self.bp_diastolic is None):
            raise ValueError("Enter both systolic and diastolic blood pressure")
        if self.bp_systolic is not None and self.bp_systolic <= self.bp_diastolic:
            raise ValueError("Systolic BP must be higher than diastolic")
        return self


class VitalsOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(validation_alias="_id")
    appointment_id: PyObjectId
    patient_id: str
    recorded_at: datetime
    recorded_by_role: str
    bp_systolic: int | None
    bp_diastolic: int | None
    pulse: int | None
    temperature_c: float | None
    spo2: int | None
    weight_kg: float | None
    height_cm: float | None
    height_carried_forward: bool = False
    bmi: float | None
    flags: dict[str, str]
    note: str | None


class VitalsTrend(BaseModel):
    patient_id: str
    paediatric: bool
    # normal range per measure for chart shading: {key: {low, high}}
    ranges: dict[str, dict[str, float | None]]
    readings: list[VitalsOut]


class ExaminationIn(BaseModel):
    text: str = Field(max_length=20000)
    dictated: bool = False


class Outcome(BaseModel):
    status: Literal["resolved", "improving", "unchanged", "worse", "referred", "admitted"]
    note: str | None = Field(None, max_length=500)


class NotesPatch(BaseModel):
    """Autosave of any subset of the free-text parts of the visit notes."""

    examination: str | None = Field(None, max_length=20000)
    dictated: bool = False
    doctor_notes: str | None = Field(None, max_length=20000)
    outcome: Outcome | None = None


class DiagnosisIn(BaseModel):
    code: str = Field(min_length=1, max_length=10)
    status: Literal["provisional", "final"] = "provisional"
    note: str | None = Field(None, max_length=500)


class DiagnosisUpdate(BaseModel):
    status: Literal["provisional", "final"] | None = None
    note: str | None = Field(None, max_length=500)


class DiagnosisOut(BaseModel):
    id: str
    code: str
    title: str
    status: Literal["provisional", "final"]
    note: str | None
    added_at: datetime
    updated_at: datetime


class NoteChange(BaseModel):
    change: str
    by_role: str
    at: datetime


class ClinicalNotesOut(BaseModel):
    appointment_id: str
    patient_id: str
    examination: str
    examination_updated_at: datetime | None
    doctor_notes: str = ""
    outcome: Outcome | None = None
    diagnoses: list[DiagnosisOut]
    changes: list[NoteChange]


class Icd10Out(BaseModel):
    code: str
    title: str
    billable: bool

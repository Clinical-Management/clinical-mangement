from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.clinical import icd10
from app.core.deps import DB, CurrentUser, require_roles
from app.core.errors import NotFound
from app.schemas.clinical import (
    ClinicalNotesOut,
    DiagnosisIn,
    DiagnosisUpdate,
    ExaminationIn,
    Icd10Out,
    VitalsIn,
    VitalsOut,
    VitalsTrend,
)
from app.schemas.user import Role
from app.services import appointment_service, clinical_service as svc

router = APIRouter(tags=["clinical"])

# Front desk records vitals at check-in; examination and diagnoses are the doctor's
VitalsWriters = Depends(require_roles(Role.ADMIN, Role.RECEPTIONIST, Role.DOCTOR))
Clinical = Depends(require_roles(Role.ADMIN, Role.DOCTOR))


async def visit(appointment_id: str, db: DB, user: CurrentUser) -> dict:
    return await appointment_service.get_for_user(db, appointment_id, user)


Visit = Annotated[dict, Depends(visit)]


def notes_out(doc: dict) -> dict:
    return {**doc, "appointment_id": str(doc["appointment_id"])}


# --- vitals ------------------------------------------------------------------


@router.post("/appointments/{appointment_id}/vitals", response_model=VitalsOut, status_code=201, dependencies=[VitalsWriters])
async def record_vitals(body: VitalsIn, appt: Visit, db: DB, user: CurrentUser):
    """Record a set of readings for this visit. BMI is computed; abnormal values are flagged,
    and critical ones raise an alert for the doctor and front desk."""
    return await svc.record_vitals(db, appt, body, user)


@router.get("/appointments/{appointment_id}/vitals", response_model=list[VitalsOut], dependencies=[VitalsWriters])
async def list_visit_vitals(appt: Visit, db: DB):
    return await svc.visit_vitals(db, appt)


@router.get("/patients/{patient_id}/vitals", response_model=VitalsTrend)
async def vitals_trend(patient_id: str, db: DB, user: CurrentUser):
    """All readings across visits, for trend charts. Patients can see their own family's."""
    if user["role"] == Role.RECEPTIONIST.value:
        raise NotFound("Patient not found")
    if user["role"] == Role.PATIENT.value and patient_id.upper() not in await appointment_service.managed_patient_ids(db, user):
        raise NotFound("Patient not found")
    return await svc.vitals_trend(db, patient_id)


# --- examination & diagnoses -------------------------------------------------


@router.get("/appointments/{appointment_id}/notes", response_model=ClinicalNotesOut, dependencies=[Clinical])
async def get_notes(appt: Visit, db: DB):
    return notes_out(await svc.get_notes(db, appt))


@router.put("/appointments/{appointment_id}/notes/examination", response_model=ClinicalNotesOut, dependencies=[Clinical])
async def save_examination(body: ExaminationIn, appt: Visit, db: DB, user: CurrentUser):
    return notes_out(await svc.save_examination(db, appt, body.text, body.dictated, user))


@router.post("/appointments/{appointment_id}/notes/diagnoses", response_model=ClinicalNotesOut, dependencies=[Clinical])
async def add_diagnosis(body: DiagnosisIn, appt: Visit, db: DB, user: CurrentUser):
    return notes_out(await svc.add_diagnosis(db, appt, body, user))


@router.patch(
    "/appointments/{appointment_id}/notes/diagnoses/{diagnosis_id}", response_model=ClinicalNotesOut, dependencies=[Clinical]
)
async def update_diagnosis(diagnosis_id: str, body: DiagnosisUpdate, appt: Visit, db: DB, user: CurrentUser):
    """Change status (provisional -> final) or the note."""
    return notes_out(await svc.update_diagnosis(db, appt, diagnosis_id, body, user))


@router.delete(
    "/appointments/{appointment_id}/notes/diagnoses/{diagnosis_id}", response_model=ClinicalNotesOut, dependencies=[Clinical]
)
async def remove_diagnosis(diagnosis_id: str, appt: Visit, db: DB, user: CurrentUser):
    return notes_out(await svc.remove_diagnosis(db, appt, diagnosis_id, user))


@router.get("/icd10", response_model=list[Icd10Out], dependencies=[Clinical])
async def search_icd10(q: str = Query(min_length=1, max_length=100), limit: int = Query(20, ge=1, le=50)):
    """Search ICD-10-CM (FY2026) by code ("E11.9", "E11") or words ("type 2 diabetes")."""
    return [{"code": c.code, "title": c.title, "billable": c.billable} for c in icd10.search(q, limit)]

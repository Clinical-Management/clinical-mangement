from typing import Annotated, Literal

from fastapi import APIRouter, Depends

from app.casesummary.writer import get_case_summary_writer
from app.core.deps import DB, CurrentUser, require_roles
from app.core.errors import NotFound
from app.schemas.case_summary import CaseSummaryOut, PrintOut, SectionsEdit
from app.schemas.user import Role
from app.services import appointment_service, case_summary_service as svc, patient_service, prescription_service, scheduling_service

router = APIRouter(tags=["case summary"])

Clinical = Depends(require_roles(Role.ADMIN, Role.DOCTOR))


def get_writer_factory():
    """Indirection so tests can swap the AI writer."""
    return get_case_summary_writer


WriterFactory = Annotated[object, Depends(get_writer_factory)]


async def visit(appointment_id: str, db: DB, user: CurrentUser) -> dict:
    return await appointment_service.get_for_user(db, appointment_id, user)


Visit = Annotated[dict, Depends(visit)]


async def existing(appt: Visit, db: DB) -> dict:
    doc = await svc.get_doc(db, appt)
    if not doc:
        raise NotFound("No case summary yet")
    return doc


Existing = Annotated[dict, Depends(existing)]


@router.get("/appointments/{appointment_id}/case-summary", response_model=CaseSummaryOut, dependencies=[Clinical])
async def get_case_summary(appt: Visit, db: DB):
    """The summary plus `stale`/`pending_changes` when history, vitals, notes, reports or the plan changed since."""
    return await svc.view(db, appt, await svc.get_doc(db, appt))


@router.post("/appointments/{appointment_id}/case-summary/generate", response_model=CaseSummaryOut, dependencies=[Clinical])
async def generate(appt: Visit, db: DB, user: CurrentUser, writer: WriterFactory):
    """Generate the first draft, or regenerate after new information. The doctor's edited sections are kept
    and the new wording is offered as a suggestion; every regeneration records what changed."""
    return await svc.view(db, appt, await svc.generate(db, appt, writer, user))


@router.put("/appointments/{appointment_id}/case-summary", response_model=CaseSummaryOut, dependencies=[Clinical])
async def edit(body: SectionsEdit, appt: Visit, doc: Existing, db: DB):
    """Free edits by the doctor (autosaved)."""
    return await svc.view(db, appt, await svc.save_sections(db, doc, body.sections))


@router.post(
    "/appointments/{appointment_id}/case-summary/suggestions/{key}/{decision}",
    response_model=CaseSummaryOut,
    dependencies=[Clinical],
)
async def resolve_suggestion(key: str, decision: Literal["accept", "dismiss"], appt: Visit, doc: Existing, db: DB):
    return await svc.view(db, appt, await svc.resolve_suggestion(db, doc, key, decision == "accept"))


@router.post("/appointments/{appointment_id}/case-summary/finalize", response_model=CaseSummaryOut, dependencies=[Clinical])
async def finalize(appt: Visit, doc: Existing, db: DB, user: CurrentUser):
    return await svc.view(db, appt, await svc.finalize(db, doc, user))


@router.post("/appointments/{appointment_id}/case-summary/reopen", response_model=CaseSummaryOut, dependencies=[Clinical])
async def reopen(appt: Visit, doc: Existing, db: DB):
    return await svc.view(db, appt, await svc.reopen(db, doc))


@router.get("/appointments/{appointment_id}/prescription/print", response_model=PrintOut, dependencies=[Clinical])
async def printable_prescription(appt: Visit, db: DB):
    """Data for the printed prescription, with the finalized case summary sections the doctor included."""
    patient = await patient_service.get_patient(db, appt["patient_id"])
    doctor = await scheduling_service.get_doctor(db, appt["doctor_id"])
    rx = await prescription_service.get(db, appt)
    doc = await svc.get_doc(db, appt)
    return {
        "clinic_name": "Clinical Management",
        "doctor_name": doctor["full_name"],
        "doctor_specialization": doctor.get("specialization"),
        "patient_name": patient["full_name"],
        "patient_id": patient["patient_id"],
        "patient_age": patient_service.current_age(patient),
        "patient_gender": patient["gender"],
        "allergies": [a["substance"] for a in (patient.get("medical") or {}).get("allergies", [])],
        "visit_date": appt["date"],
        "token": appt.get("token"),
        "case_summary": await svc.finalized_sections(db, appt, rx.get("summary_sections")),
        "case_summary_status": doc["status"] if doc else None,
        "prescription": {k: rx.get(k) for k in ("medicines", "investigations", "advice", "diet_lifestyle", "referral", "follow_up")},
    }

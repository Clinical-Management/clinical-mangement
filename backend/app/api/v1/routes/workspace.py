from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import DB, CurrentUser, require_roles
from app.schemas.user import Role
from app.services import appointment_service, report_service, visit_service

router = APIRouter(tags=["case workspace"])

Clinical = Depends(require_roles(Role.ADMIN, Role.DOCTOR))


async def visit(appointment_id: str, db: DB, user: CurrentUser) -> dict:
    return await appointment_service.get_for_user(db, appointment_id, user)


Visit = Annotated[dict, Depends(visit)]


# --- past visits -------------------------------------------------------------


@router.get("/patients/{patient_id}/visits", dependencies=[Clinical])
async def past_visits(patient_id: str, db: DB, user: CurrentUser, exclude: str | None = None):
    """Earlier completed visits across doctors: complaint, findings, diagnoses, prescription, outcome."""
    patient = await report_service.patient_for(db, patient_id, user)
    return await visit_service.past_visits(db, patient["patient_id"], exclude_appointment=exclude)

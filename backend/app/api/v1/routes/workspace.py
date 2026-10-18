from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import DB, CurrentUser, require_roles
from app.schemas.billing import BillIn, BillOut, PayIn, WaiveIn
from app.schemas.prescription import PrescriptionIn, PrescriptionOut
from app.schemas.user import Role
from app.services import appointment_service, billing_service, prescription_service, report_service, visit_service

router = APIRouter(tags=["case workspace"])

Clinical = Depends(require_roles(Role.ADMIN, Role.DOCTOR))
Billing = Depends(require_roles(Role.ADMIN, Role.RECEPTIONIST, Role.DOCTOR))


async def visit(appointment_id: str, db: DB, user: CurrentUser) -> dict:
    return await appointment_service.get_for_user(db, appointment_id, user)


Visit = Annotated[dict, Depends(visit)]


# --- prescription ------------------------------------------------------------


@router.get("/appointments/{appointment_id}/prescription", response_model=PrescriptionOut, dependencies=[Clinical])
async def get_prescription(appt: Visit, db: DB):
    return await prescription_service.get(db, appt)


@router.put("/appointments/{appointment_id}/prescription", response_model=PrescriptionOut, dependencies=[Clinical])
async def save_prescription(body: PrescriptionIn, appt: Visit, db: DB, user: CurrentUser):
    """Autosaved as a whole: medicines, investigations, advice and follow-up.
    Returns allergy warnings for medicines that match the patient's recorded allergies."""
    return await prescription_service.save(db, appt, body, user)


# --- billing -----------------------------------------------------------------


@router.get("/appointments/{appointment_id}/bill", response_model=BillOut, dependencies=[Billing])
async def get_bill(appt: Visit, db: DB):
    """Charges for this visit; the consultation line is filled from the doctor's fee for the visit type."""
    return await billing_service.get_bill(db, appt)


@router.put("/appointments/{appointment_id}/bill", response_model=BillOut, dependencies=[Billing])
async def save_bill(body: BillIn, appt: Visit, db: DB):
    return await billing_service.save_bill(db, appt, body)


@router.post("/appointments/{appointment_id}/bill/pay", response_model=BillOut, dependencies=[Billing])
async def pay_bill(body: PayIn, appt: Visit, db: DB, user: CurrentUser):
    """Marks the visit paid, which also starts the follow-up window for free follow-ups."""
    return await billing_service.pay(db, appt, body.mode, user)


@router.post("/appointments/{appointment_id}/bill/waive", response_model=BillOut, dependencies=[Billing])
async def waive_bill(body: WaiveIn, appt: Visit, db: DB, user: CurrentUser):
    return await billing_service.waive(db, appt, body.reason, user)


# --- past visits -------------------------------------------------------------


@router.get("/patients/{patient_id}/visits", dependencies=[Clinical])
async def past_visits(patient_id: str, db: DB, user: CurrentUser, exclude: str | None = None):
    """Earlier completed visits across doctors: complaint, findings, diagnoses, prescription, outcome."""
    patient = await report_service.patient_for(db, patient_id, user)
    return await visit_service.past_visits(db, patient["patient_id"], exclude_appointment=exclude)

from fastapi import APIRouter

from app.api.v1.routes import (
    admin,
    appointments,
    auth,
    billing,
    case_summary,
    clinical,
    doctor,
    doctors,
    history,
    holidays,
    ml,
    patient,
    patients,
    prescriptions,
    receptionist,
    reports,
    summaries,
    workspace,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(doctor.router)
api_router.include_router(patient.router)
api_router.include_router(receptionist.router)
api_router.include_router(patients.router)
api_router.include_router(doctors.router)
api_router.include_router(holidays.router)
api_router.include_router(appointments.router)
api_router.include_router(history.router)
api_router.include_router(clinical.router)
api_router.include_router(reports.router)
api_router.include_router(summaries.router)
api_router.include_router(workspace.router)
api_router.include_router(case_summary.router)
api_router.include_router(prescriptions.router)
api_router.include_router(billing.router)
api_router.include_router(ml.router)

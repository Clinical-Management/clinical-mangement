from fastapi import APIRouter

from app.api.v1.routes import (
    admin,
    appointments,
    auth,
    clinical,
    doctor,
    doctors,
    history,
    holidays,
    ml,
    patient,
    patients,
    receptionist,
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
api_router.include_router(ml.router)

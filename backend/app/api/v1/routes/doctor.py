from fastapi import APIRouter, Depends

from app.core.deps import require_roles
from app.schemas.user import Role

router = APIRouter(prefix="/doctor", tags=["doctor"], dependencies=[Depends(require_roles(Role.DOCTOR))])

# Doctor features (appointments, prescriptions, patient records, ...) go here.

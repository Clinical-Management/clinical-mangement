from fastapi import APIRouter, Depends

from app.core.deps import require_roles
from app.schemas.user import Role

router = APIRouter(prefix="/patient", tags=["patient"], dependencies=[Depends(require_roles(Role.PATIENT))])

# Patient features (booking, medical history, reports, ...) go here.

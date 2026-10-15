from fastapi import APIRouter, Depends

from app.core.deps import require_roles
from app.schemas.user import Role

router = APIRouter(
    prefix="/receptionist", tags=["receptionist"], dependencies=[Depends(require_roles(Role.RECEPTIONIST))]
)

# Front-desk features (check-in queue, appointment booking, billing, ...) go here.

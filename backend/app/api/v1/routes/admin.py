from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import DB, require_roles
from app.schemas.user import Role, UserCreate, UserOut
from app.services.user_service import EmailAlreadyRegistered, create_user

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_roles(Role.ADMIN))])


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_any_user(body: UserCreate, db: DB):
    """Create doctors (or other admins/patients) on their behalf."""
    try:
        return await create_user(db, email=body.email, full_name=body.full_name, password=body.password, role=body.role)
    except EmailAlreadyRegistered:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")


@router.get("/users", response_model=list[UserOut])
async def list_users(
    db: DB,
    role: Role | None = None,
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
):
    query = {"role": role.value} if role else {}
    return await db.users.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list()

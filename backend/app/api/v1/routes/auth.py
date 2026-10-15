from fastapi import APIRouter, HTTPException, status

from app.core.deps import DB, CurrentUser
from app.core.security import create_access_token
from app.schemas.user import LoginRequest, PatientRegister, Role, TokenResponse, UserOut
from app.services.user_service import EmailAlreadyRegistered, authenticate, create_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register_patient(body: PatientRegister, db: DB):
    """Public self-registration. Always creates a patient account."""
    try:
        return await create_user(db, email=body.email, full_name=body.full_name, password=body.password, role=Role.PATIENT)
    except EmailAlreadyRegistered:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: DB):
    user = await authenticate(db, body.email, body.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    token = create_access_token(str(user["_id"]), user["role"])
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user

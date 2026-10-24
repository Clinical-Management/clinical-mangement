import time
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials

from app.core.config import settings
from app.core.deps import DB, CurrentUser, bearer_scheme
from app.core.security import create_access_token, create_mfa_token, decode_access_token, decode_mfa_token
from app.schemas.user import LoginRequest, MfaCode, MfaEnabled, MfaToken, PatientRegister, Role, TokenResponse, UserOut
from app.services import audit_service, mfa_service
from app.services.user_service import (
    EmailAlreadyRegistered,
    authenticate,
    clear_failed_logins,
    create_user,
    get_user_by_id,
    is_locked,
    record_failed_login,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _ip(request: Request) -> str | None:
    return request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client and request.client.host)


def _session(user: dict, auth_time: int | None = None) -> TokenResponse:
    return TokenResponse(access_token=create_access_token(str(user["_id"]), user["role"], auth_time), user=UserOut.model_validate(user))


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register_patient(body: PatientRegister, db: DB):
    """Public self-registration. Always creates a patient account."""
    try:
        return await create_user(db, email=body.email, full_name=body.full_name, password=body.password, role=Role.PATIENT)
    except EmailAlreadyRegistered:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: DB, request: Request):
    """Patients get a session straight away. Staff then enter a code from their authenticator app
    (or set one up first, when the clinic requires it)."""
    user = await authenticate(db, body.email, body.password)
    if user is None:
        await record_failed_login(db, body.email)
        await audit_service.record(db, actor=None, action="login_failed", resource="auth", details={"email": body.email.lower()}, ip=_ip(request))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if mfa_service.is_staff(user):
        if mfa_service.enabled(user):
            return TokenResponse(mfa_required=True, mfa_token=create_mfa_token(str(user["_id"])))
        if await mfa_service.required(db):
            return TokenResponse(mfa_setup_required=True, mfa_token=create_mfa_token(str(user["_id"])))
    await clear_failed_logins(db, user)
    await audit_service.record(db, actor=user, action="login", resource="auth", ip=_ip(request))
    return _session(user)


async def _mfa_user(db, mfa_token: str | None, credentials: HTTPAuthorizationCredentials | None) -> tuple[dict, bool]:
    """The user mid-sign-in (MFA token) or already signed in (bearer token); True if mid-sign-in."""
    try:
        if mfa_token:
            user = await get_user_by_id(db, decode_mfa_token(mfa_token)["sub"])
            signing_in = True
        elif credentials:
            user = await get_user_by_id(db, decode_access_token(credentials.credentials)["sub"])
            signing_in = False
        else:
            user = None
    except jwt.PyJWTError:
        user = None
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your sign-in expired. Please sign in again.")
    return user, signing_in


Bearer = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


@router.post("/mfa/verify", response_model=TokenResponse)
async def mfa_verify(body: MfaCode, db: DB, request: Request):
    """Second step of a staff sign-in: a 6-digit authenticator code or a recovery code."""
    user, _ = await _mfa_user(db, body.mfa_token, None)
    if is_locked(user) or not await mfa_service.check(db, user, body.code):
        await record_failed_login(db, user["email"])
        await audit_service.record(db, actor=user, action="mfa_failed", resource="auth", ip=_ip(request))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="That code didn't work. Try the newest code from the app.")
    await clear_failed_logins(db, user)
    await audit_service.record(db, actor=user, action="login", resource="auth", details={"mfa": True}, ip=_ip(request))
    return _session(user)


@router.post("/mfa/setup")
async def mfa_setup(body: MfaToken, db: DB, credentials: Bearer):
    """Secret and QR code to scan with an authenticator app."""
    user, _ = await _mfa_user(db, body.mfa_token, credentials)
    if not mfa_service.is_staff(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Two-step sign-in is for staff accounts")
    return await mfa_service.start_setup(db, user)


@router.post("/mfa/enable", response_model=MfaEnabled)
async def mfa_enable(body: MfaCode, db: DB, credentials: Bearer, request: Request):
    """Confirms the app works; returns one-time recovery codes (shown once) and, mid-sign-in, the session."""
    user, signing_in = await _mfa_user(db, body.mfa_token, credentials)
    codes = await mfa_service.confirm_setup(db, user, body.code)
    if signing_in:
        await clear_failed_logins(db, user)
    await audit_service.record(db, actor=user, action="mfa_enabled", resource="auth", ip=_ip(request))
    return MfaEnabled(recovery_codes=codes, session=_session(await get_user_by_id(db, str(user["_id"]))) if signing_in else None)


@router.post("/mfa/disable", status_code=204)
async def mfa_disable(body: MfaCode, db: DB, user: CurrentUser, request: Request):
    """Turn off (e.g. to move to a new phone). If the clinic requires it, setup is asked again at next sign-in."""
    if not await mfa_service.check(db, user, body.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That code didn't work")
    await mfa_service.disable(db, user["_id"])
    await audit_service.record(db, actor=user, action="mfa_disabled", resource="auth", ip=_ip(request))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(db: DB, user: CurrentUser, credentials: Bearer):
    """Called by the app while the user is active, so idle sessions expire but active ones don't.
    Staff must sign in again after the absolute session limit."""
    claims = decode_access_token(credentials.credentials)
    auth_time = claims.get("auth_time", int(time.time()))
    if mfa_service.is_staff(user) and time.time() - auth_time > settings.staff_session_max_hours * 3600:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session limit reached. Please sign in again.")
    return _session(user, auth_time)


@router.post("/logout", status_code=204)
async def logout(db: DB, user: CurrentUser, request: Request):
    await audit_service.record(db, actor=user, action="logout", resource="auth", ip=_ip(request))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user

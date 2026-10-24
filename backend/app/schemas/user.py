from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.schemas.common import PyObjectId


class Role(str, Enum):
    ADMIN = "admin"
    DOCTOR = "doctor"
    RECEPTIONIST = "receptionist"
    PATIENT = "patient"


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)


class PatientRegister(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserCreate(PatientRegister):
    """Admin-only: create a user with any role (e.g. doctors)."""

    role: Role


class UserOut(UserBase):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(validation_alias="_id")
    role: Role
    is_active: bool = True
    created_at: datetime
    mfa_enabled: bool = False

    @model_validator(mode="before")
    @classmethod
    def _mfa(cls, data):
        if isinstance(data, dict) and "mfa_enabled" not in data:
            data = {**data, "mfa_enabled": bool((data.get("mfa") or {}).get("enabled"))}
        return data


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Either a session (access_token + user) or, for staff, a request for the second factor."""

    access_token: str | None = None
    token_type: str = "bearer"
    user: UserOut | None = None
    mfa_required: bool = False  # enter the code from the authenticator app
    mfa_setup_required: bool = False  # set up an authenticator app first
    mfa_token: str | None = None


class MfaCode(BaseModel):
    code: str = Field(min_length=6, max_length=12)
    mfa_token: str | None = None  # during sign-in; omitted when already signed in


class MfaToken(BaseModel):
    mfa_token: str | None = None


class MfaEnabled(BaseModel):
    recovery_codes: list[str]
    session: TokenResponse | None = None


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=120)
    role: Role | None = None
    is_active: bool | None = None


class PasswordReset(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class SecuritySettings(BaseModel):
    staff_mfa_required: bool

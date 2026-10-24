import time
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings

STAFF_ROLES = {"admin", "doctor", "receptionist"}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def session_minutes(role: str) -> int:
    """Staff sessions end after a short idle period (the app refreshes the token while in use);
    patients stay signed in longer on their own phone."""
    return settings.staff_idle_minutes if role in STAFF_ROLES else settings.patient_session_minutes


def create_access_token(subject: str, role: str, auth_time: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=session_minutes(role)),
        "auth_time": auth_time or int(time.time()),  # when the user last entered their password
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_mfa_token(subject: str) -> str:
    """Short-lived proof that the password was right; only exchangeable for a session after the second factor."""
    now = datetime.now(timezone.utc)
    payload = {"sub": subject, "purpose": "mfa", "iat": now, "exp": now + timedelta(minutes=10)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError if the token is invalid, expired or not a session token."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("purpose", "access") != "access":
        raise jwt.InvalidTokenError("Not a session token")
    return payload


def decode_mfa_token(token: str) -> dict:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("purpose") != "mfa":
        raise jwt.InvalidTokenError("Not an MFA token")
    return payload

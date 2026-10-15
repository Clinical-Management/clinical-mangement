from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pymongo.asynchronous.database import AsyncDatabase

from app.core.security import decode_access_token
from app.db.mongodb import get_db
from app.schemas.user import Role
from app.services.user_service import get_user_by_id

bearer_scheme = HTTPBearer(auto_error=False)

DB = Annotated[AsyncDatabase, Depends(get_db)]


async def get_current_user(
    db: DB,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> dict:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError:
        raise unauthorized

    user = await get_user_by_id(db, payload.get("sub", ""))
    if user is None or not user.get("is_active"):
        raise unauthorized
    return user


CurrentUser = Annotated[dict, Depends(get_current_user)]


def require_roles(*roles: Role):
    """Dependency factory: `Depends(require_roles(Role.ADMIN, Role.DOCTOR))`."""
    allowed = {r.value for r in roles}

    async def checker(user: CurrentUser) -> dict:
        if user["role"] not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return checker

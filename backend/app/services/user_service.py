from datetime import datetime, timezone

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.security import hash_password, verify_password
from app.schemas.common import parse_object_id
from app.schemas.user import Role


class EmailAlreadyRegistered(Exception):
    pass


async def create_user(db: AsyncDatabase, *, email: str, full_name: str, password: str, role: Role) -> dict:
    doc = {
        "email": email.lower(),
        "full_name": full_name,
        "password_hash": hash_password(password),
        "role": role.value,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }
    try:
        result = await db.users.insert_one(doc)
    except DuplicateKeyError as exc:
        raise EmailAlreadyRegistered from exc
    doc["_id"] = result.inserted_id
    return doc


async def get_user_by_id(db: AsyncDatabase, user_id: str) -> dict | None:
    oid = parse_object_id(user_id)
    return await db.users.find_one({"_id": oid}) if oid else None


async def authenticate(db: AsyncDatabase, email: str, password: str) -> dict | None:
    user = await db.users.find_one({"email": email.lower()})
    if user and user.get("is_active") and verify_password(password, user["password_hash"]):
        return user
    return None

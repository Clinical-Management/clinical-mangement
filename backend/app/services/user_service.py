from datetime import datetime, timedelta, timezone

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


LOCKOUT_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def is_locked(user: dict) -> bool:
    locked = user.get("locked_until")
    return bool(locked and (locked if locked.tzinfo else locked.replace(tzinfo=timezone.utc)) > datetime.now(timezone.utc))


async def authenticate(db: AsyncDatabase, email: str, password: str) -> dict | None:
    """None for a wrong password, an inactive account, or while locked after repeated failures."""
    user = await db.users.find_one({"email": email.lower()})
    if not user or not user.get("is_active"):
        return None
    if is_locked(user):
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return user


async def clear_failed_logins(db: AsyncDatabase, user: dict) -> None:
    """After a complete sign-in (password and, for staff, the second factor)."""
    await db.users.update_one({"_id": user["_id"]}, {"$unset": {"failed_logins": "", "locked_until": ""}})


async def record_failed_login(db: AsyncDatabase, email: str) -> None:
    """Locks the account for a while after repeated wrong passwords or codes (slows down guessing)."""
    user = await db.users.find_one_and_update({"email": email.lower()}, {"$inc": {"failed_logins": 1}}, return_document=True)
    if user and user.get("failed_logins", 0) >= LOCKOUT_ATTEMPTS:
        await db.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"locked_until": datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES), "failed_logins": 0}},
        )

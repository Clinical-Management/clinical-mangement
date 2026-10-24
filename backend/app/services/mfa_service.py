"""Staff multi-factor authentication: authenticator-app codes plus one-time recovery codes."""

import base64
import hashlib
import io
import secrets
from datetime import datetime, timezone

import qrcode
from pymongo.asynchronous.database import AsyncDatabase

from app.core import totp
from app.core.config import settings
from app.core.crypto import decrypt_text, encrypt_text
from app.core.errors import Conflict, Invalid
from app.core.security import STAFF_ROLES

RECOVERY_CODES = 8


def _hash(code: str) -> str:
    return hashlib.sha256(code.replace("-", "").strip().lower().encode()).hexdigest()


def is_staff(user: dict) -> bool:
    return user["role"] in STAFF_ROLES


def enabled(user: dict) -> bool:
    return bool((user.get("mfa") or {}).get("enabled"))


async def required(db: AsyncDatabase) -> bool:
    doc = await db.settings.find_one({"_id": "security"}) or {}
    return doc.get("staff_mfa_required", settings.staff_mfa_required)


async def start_setup(db: AsyncDatabase, user: dict) -> dict:
    """New secret (not active until a code from the app is confirmed) and a QR code to scan."""
    if enabled(user):
        raise Conflict("Two-step sign-in is already on. Turn it off first to switch phones.")
    secret = totp.new_secret()
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"mfa.pending_secret": encrypt_text(secret)}})
    uri = totp.provisioning_uri(secret, user["email"], settings.app_name.replace(" API", ""))
    png = io.BytesIO()
    qrcode.make(uri, box_size=6, border=2).save(png, format="PNG")
    return {"secret": secret, "otpauth_uri": uri, "qr_png": "data:image/png;base64," + base64.b64encode(png.getvalue()).decode()}


async def confirm_setup(db: AsyncDatabase, user: dict, code: str) -> list[str]:
    pending = (user.get("mfa") or {}).get("pending_secret")
    if not pending:
        raise Invalid("Start the setup again")
    secret = decrypt_text(pending)
    step = totp.verify(secret, code)
    if step is None:
        raise Invalid("That code didn't match. Check the phone's time is set automatically and try the newest code.")
    codes = [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(RECOVERY_CODES)]
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"mfa": {"enabled": True, "secret": pending, "last_step": step, "recovery": [_hash(c) for c in codes],
                          "enabled_at": datetime.now(timezone.utc)}}},
    )
    return codes


async def check(db: AsyncDatabase, user: dict, code: str) -> bool:
    """An authenticator code (each usable once) or an unused recovery code."""
    mfa = user.get("mfa") or {}
    if not mfa.get("enabled"):
        return False
    step = totp.verify(decrypt_text(mfa["secret"]), code)
    if step is not None:
        # atomic: the same code can't be used twice, even by two requests at once
        result = await db.users.update_one(
            {"_id": user["_id"], "$or": [{"mfa.last_step": {"$lt": step}}, {"mfa.last_step": {"$exists": False}}]},
            {"$set": {"mfa.last_step": step}},
        )
        return result.modified_count == 1
    result = await db.users.update_one({"_id": user["_id"], "mfa.recovery": _hash(code)}, {"$pull": {"mfa.recovery": _hash(code)}})
    return result.modified_count == 1


async def disable(db: AsyncDatabase, user_id) -> None:
    await db.users.update_one({"_id": user_id}, {"$unset": {"mfa": ""}})

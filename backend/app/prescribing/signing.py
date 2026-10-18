"""Tamper-evident signature for finalized prescriptions.

Each finalized version is hashed (canonical JSON of its content) and signed with HMAC-SHA256 using
PRESCRIPTION_SIGNING_KEY. The QR code on the PDF links to a public page that recomputes the
signature, so a pharmacist can confirm the prescription is genuine and is the current version.
"""

import hashlib
import hmac
import json
import secrets

from app.core.config import settings


def _key() -> bytes:
    return (settings.prescription_signing_key or settings.jwt_secret).encode()


def content_hash(content: dict) -> str:
    return hashlib.sha256(json.dumps(content, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def sign(content: dict) -> str:
    return hmac.new(_key(), content_hash(content).encode(), hashlib.sha256).hexdigest()


def verify(content: dict, signature: str) -> bool:
    return hmac.compare_digest(sign(content), signature)


def public_id() -> str:
    """Short, unguessable id printed under the QR code."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "RX-" + "".join(secrets.choice(alphabet) for _ in range(10))

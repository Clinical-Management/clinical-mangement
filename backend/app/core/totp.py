"""Time-based one-time passwords (RFC 6238) for staff multi-factor authentication.

Works with Google Authenticator, Microsoft Authenticator, Authy and similar apps."""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

DIGITS = 6
PERIOD = 30


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def now_code(secret: str, at: float | None = None) -> str:
    return _code(secret, int((at or time.time()) // PERIOD))


def verify(secret: str, code: str, at: float | None = None, window: int = 1) -> int | None:
    """Returns the matched time step (so a code can't be reused), or None.
    Accepts one step either side for clock drift."""
    code = "".join(c for c in code if c.isdigit())
    if len(code) != DIGITS:
        return None
    step = int((at or time.time()) // PERIOD)
    for s in range(step - window, step + window + 1):
        if hmac.compare_digest(_code(secret, s), code):
            return s
    return None


def provisioning_uri(secret: str, account: str, issuer: str) -> str:
    label = quote(f"{issuer}:{account}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&digits={DIGITS}&period={PERIOD}"

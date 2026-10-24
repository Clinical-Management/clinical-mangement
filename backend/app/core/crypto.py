"""Application-level encryption at rest (AES-256-GCM) for secrets and stored files.

The key comes from DATA_ENCRYPTION_KEY (32 bytes, base64). Without it a key is derived from JWT_SECRET so
development works, but production must set a dedicated key and keep it backed up: data encrypted with a
lost key cannot be recovered."""

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

MAGIC = b"CMENC1"  # marks encrypted blobs, so files stored before encryption was enabled still read


def _key() -> bytes:
    if settings.data_encryption_key:
        key = base64.b64decode(settings.data_encryption_key)
        if len(key) != 32:
            raise ValueError("DATA_ENCRYPTION_KEY must be 32 bytes, base64 encoded")
        return key
    return hashlib.sha256(b"data-encryption:" + settings.jwt_secret.encode()).digest()


def encrypt(data: bytes) -> bytes:
    nonce = os.urandom(12)
    return MAGIC + nonce + AESGCM(_key()).encrypt(nonce, data, MAGIC)


def decrypt(blob: bytes) -> bytes:
    if not blob.startswith(MAGIC):
        return blob  # stored before encryption at rest was added
    nonce = blob[len(MAGIC) : len(MAGIC) + 12]
    return AESGCM(_key()).decrypt(nonce, blob[len(MAGIC) + 12 :], MAGIC)


def encrypt_text(text: str) -> str:
    return base64.b64encode(encrypt(text.encode())).decode()


def decrypt_text(token: str) -> str:
    return decrypt(base64.b64decode(token)).decode()

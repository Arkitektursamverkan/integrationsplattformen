"""Encrypt/decrypt external system credentials using Fernet symmetric encryption."""
from __future__ import annotations

import base64
import hashlib
import json

from cryptography.fernet import Fernet

from app.config import settings


def _get_fernet() -> Fernet:
    # Derive a valid 32-byte key from the config string
    key_bytes = hashlib.sha256(settings.ENCRYPTION_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def encrypt_credentials(credentials: dict) -> bytes:
    f = _get_fernet()
    return f.encrypt(json.dumps(credentials).encode())


def decrypt_credentials(encrypted: bytes) -> dict:
    f = _get_fernet()
    return json.loads(f.decrypt(encrypted).decode())

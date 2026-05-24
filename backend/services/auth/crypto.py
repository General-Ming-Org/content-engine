"""Fernet symmetric encryption for sensitive credentials stored in DB.

The key is derived from APP_SECRET_KEY so we don't need a separate KMS for a
single-deployment system. Rotating APP_SECRET_KEY invalidates all existing
encrypted blobs — re-encrypt or have users re-enter creds after rotation.

Usage:
    cipher = encrypt(plaintext_dict_or_str)   # → str (urlsafe base64)
    plain  = decrypt(cipher)                  # → original str or dict
"""
import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet

from config import get_settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        secret = get_settings().app_secret_key.encode("utf-8")
        # Derive a 32-byte key from APP_SECRET_KEY via SHA-256 → urlsafe base64
        key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
        _fernet = Fernet(key)
    return _fernet


def encrypt(value: Any) -> str:
    """Encrypts a string, dict, or any JSON-serializable structure."""
    payload = value if isinstance(value, str) else json.dumps(value, separators=(",", ":"))
    return _get_fernet().encrypt(payload.encode("utf-8")).decode("ascii")


def decrypt(cipher: str | None) -> Any:
    """Returns a dict if the encrypted value is JSON, otherwise a plain string."""
    if not cipher:
        return None
    raw = _get_fernet().decrypt(cipher.encode("ascii")).decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw

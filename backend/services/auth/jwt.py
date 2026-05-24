"""JWT issuance and verification. HS256 with APP_SECRET_KEY. 24-hour TTL."""
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from jose import JWTError, jwt

from config import get_settings

ALGORITHM = "HS256"
ACCESS_TOKEN_TTL_HOURS = 24


def create_access_token(user_id: UUID, role: str) -> tuple[str, datetime]:
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_TTL_HOURS)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": datetime.now(timezone.utc),
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.app_secret_key, algorithm=ALGORITHM)
    return token, expires_at


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.app_secret_key, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise ValueError(f"Invalid token: {exc}") from exc

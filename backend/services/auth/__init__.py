"""Auth service — signup, login, JWT issuance, and FastAPI dependencies."""
from services.auth.deps import get_current_user, get_current_user_optional, require_verified_user
from services.auth.jwt import create_access_token, decode_token
from services.auth.password import hash_password, verify_password

__all__ = [
    "create_access_token",
    "decode_token",
    "get_current_user",
    "get_current_user_optional",
    "hash_password",
    "require_verified_user",
    "verify_password",
]

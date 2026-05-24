"""Auth: email/password signup, bcrypt hashing, JWT issuance, current-user resolution.

Public surface:
  - router       — mountable at /api/auth
  - get_current_user, require_admin — FastAPI dependencies for protected routes
  - encrypt / decrypt — Fernet wrappers for storing sensitive credentials in DB
"""
from services.auth.crypto import decrypt, encrypt
from services.auth.deps import get_current_user, get_current_user_optional, require_admin
from services.auth.router import router

__all__ = [
    "router",
    "get_current_user",
    "get_current_user_optional",
    "require_admin",
    "encrypt",
    "decrypt",
]

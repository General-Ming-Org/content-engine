import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base

UserRoleEnum = Enum("admin", "user", name="user_role_enum")


class User(Base):
    """A single deployment of Content Engine supports multiple users; each posts
    to their own LinkedIn / Substack accounts. AI keys and infrastructure are
    operator-paid (env-config); user-specific credentials live in user_credentials.

    First account created is automatically promoted to `admin`."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(UserRoleEnum, nullable=False, default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Email verification — non-blocking: the user can use the app, but a banner
    # is shown until they click the link in their inbox. Token is the SHA-256
    # hash of the random URL token (we never store raw tokens).
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_verification_token_hash: Mapped[str | None] = mapped_column(Text)
    email_verification_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base

CredentialProviderEnum = Enum(
    "linkedin",
    "linkedin_app",
    "substack",
    "smtp",
    "mcp_token",
    name="credential_provider_enum",
)


class UserCredential(Base):
    """Per-user platform credentials. Sensitive fields (refresh tokens, passwords)
    are encrypted at application layer via services.auth.crypto before insertion.
    The `secret_payload` JSONB stores the encrypted blob; `metadata_payload`
    stores non-sensitive context (e.g. linkedin_person_urn, publication_url).

    One row per (user_id, provider). Updating overwrites — no version history."""

    __tablename__ = "user_credentials"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_user_credentials"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(CredentialProviderEnum, nullable=False)
    secret_payload: Mapped[str | None] = mapped_column(Text)            # Fernet-encrypted ciphertext
    metadata_payload: Mapped[dict | None] = mapped_column(JSONB)        # plaintext (non-sensitive)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

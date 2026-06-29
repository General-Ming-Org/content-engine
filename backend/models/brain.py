"""Research Brain ORM models."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from models.db_types import JsonDocument, StringList

InspirationStatusEnum = Enum(
    "new", "processed", "archived", name="inspiration_status_enum"
)


class InspirationPost(Base):
    __tablename__ = "inspiration_posts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    author_handle: Mapped[str | None] = mapped_column(Text)
    hook_text: Mapped[str] = mapped_column(Text, nullable=False)
    full_text: Mapped[str | None] = mapped_column(Text)
    focus_area: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    traction_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pattern_tags: Mapped[dict | None] = mapped_column(JsonDocument)
    harvested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(
        InspirationStatusEnum, nullable=False, default="new"
    )


class UserVoiceProfile(Base):
    __tablename__ = "user_voice_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    personality_summary: Mapped[str | None] = mapped_column(Text)
    hook_affinites: Mapped[dict | None] = mapped_column(JsonDocument)
    structural_preferences: Mapped[dict | None] = mapped_column(JsonDocument)
    sample_phrases: Mapped[list[str] | None] = mapped_column(StringList)
    focus_areas: Mapped[list[str] | None] = mapped_column(StringList)
    bio_context: Mapped[str | None] = mapped_column(Text)
    insights: Mapped[dict | None] = mapped_column(JsonDocument)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

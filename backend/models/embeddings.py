import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base

EmbeddingKindEnum = Enum(
    "research", "posts", "articles", "sources",
    name="embedding_kind_enum",
)


class EmbeddingRecord(Base):
    """Bookkeeping for vectors stored in Qdrant.

    `user_id` is nullable: KIND_RESEARCH is a shared pool (no owner) while
    KIND_POSTS / KIND_ARTICLES are per-user. The re-embed task uses user_id to
    scope batch jobs (each user's content is re-embedded independently).
    """

    __tablename__ = "embedding_records"
    __table_args__ = (
        UniqueConstraint("doc_id", "kind", "embedding_model_id", name="uq_embedding_record"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    doc_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(EmbeddingKindEnum, nullable=False, index=True)
    embedding_model_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    source_text_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

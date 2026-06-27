import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.db_types import JsonDocument, StringList

VoiceStyleEnum = Enum("opinionated", "analytical", "tutorial", name="voice_style_enum")
PostStatusEnum = Enum(
    "draft", "queued", "scheduled", "published", "failed", "cancelled",
    name="post_status_enum",
)
ArticleStatusEnum = Enum(
    "draft", "queued", "scheduled", "published", "failed", "cancelled",
    name="article_status_enum",
)


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    research_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_topics.id", ondelete="SET NULL"), nullable=True
    )
    linked_article_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articles.id", ondelete="SET NULL"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    hashtags: Mapped[list[str] | None] = mapped_column(StringList)
    voice_style: Mapped[str] = mapped_column(VoiceStyleEnum, nullable=False)
    status: Mapped[str] = mapped_column(PostStatusEnum, nullable=False, default="draft")
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    linkedin_post_id: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[dict | None] = mapped_column(JsonDocument)
    is_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    linked_article: Mapped["Article | None"] = relationship(
        "Article", foreign_keys=[linked_article_id]
    )


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    research_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("research_topics.id", ondelete="SET NULL"), nullable=True
    )
    linked_post_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle: Mapped[str | None] = mapped_column(Text)
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    voice_style: Mapped[str] = mapped_column(VoiceStyleEnum, nullable=False)
    status: Mapped[str] = mapped_column(ArticleStatusEnum, nullable=False, default="draft")
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    substack_url: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[dict | None] = mapped_column(JsonDocument)
    is_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    linked_post: Mapped["Post | None"] = relationship(
        "Post", foreign_keys=[linked_post_id]
    )

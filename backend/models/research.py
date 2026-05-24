import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base

DomainEnum = Enum("ai_ml", "software_eng", "sre_infra", "data_eng", name="domain_enum")
ResearchStatusEnum = Enum("new", "assigned", "used", "archived", name="research_status_enum")


class ResearchTopic(Base):
    __tablename__ = "research_topics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    sources: Mapped[dict | None] = mapped_column(JSONB)
    domain: Mapped[str] = mapped_column(DomainEnum, nullable=False)
    relevance_score: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(ResearchStatusEnum, nullable=False, default="new")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

"""Embedding records bookkeeping table

Revision ID: 002
Revises: 001
Create Date: 2026-05-23 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE embedding_kind_enum AS ENUM ('research', 'posts', 'articles', 'sources')")

    op.create_table(
        "embedding_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("doc_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM("research", "posts", "articles", "sources", name="embedding_kind_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("embedding_model_id", sa.Text(), nullable=False),
        sa.Column("source_text_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("doc_id", "kind", "embedding_model_id", name="uq_embedding_record"),
    )
    op.create_index("ix_embedding_records_doc_id", "embedding_records", ["doc_id"])
    op.create_index("ix_embedding_records_kind", "embedding_records", ["kind"])
    op.create_index(
        "ix_embedding_records_model", "embedding_records", ["embedding_model_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_embedding_records_model", table_name="embedding_records")
    op.drop_index("ix_embedding_records_kind", table_name="embedding_records")
    op.drop_index("ix_embedding_records_doc_id", table_name="embedding_records")
    op.drop_table("embedding_records")
    op.execute("DROP TYPE embedding_kind_enum")

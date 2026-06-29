"""Add Research Brain tables — inspiration_posts and user_voice_profiles.

Revision ID: 006
Revises: 005
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE inspiration_status_enum AS ENUM ('new', 'processed', 'archived')"
    )
    op.create_table(
        "inspiration_posts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("author_handle", sa.Text(), nullable=True),
        sa.Column("hook_text", sa.Text(), nullable=False),
        sa.Column("full_text", sa.Text(), nullable=True),
        sa.Column("focus_area", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("traction_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("pattern_tags", postgresql.JSONB(), nullable=True),
        sa.Column(
            "harvested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "new", "processed", "archived",
                name="inspiration_status_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="new",
        ),
    )
    op.create_index("ix_inspiration_posts_url", "inspiration_posts", ["url"], unique=True)
    op.create_index("ix_inspiration_posts_traction", "inspiration_posts", ["traction_score"])

    op.create_table(
        "user_voice_profiles",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("personality_summary", sa.Text(), nullable=True),
        sa.Column("hook_affinites", postgresql.JSONB(), nullable=True),
        sa.Column("structural_preferences", postgresql.JSONB(), nullable=True),
        sa.Column("sample_phrases", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("focus_areas", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("bio_context", sa.Text(), nullable=True),
        sa.Column("insights", postgresql.JSONB(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("user_voice_profiles")
    op.drop_index("ix_inspiration_posts_traction", table_name="inspiration_posts")
    op.drop_index("ix_inspiration_posts_url", table_name="inspiration_posts")
    op.drop_table("inspiration_posts")
    op.execute("DROP TYPE inspiration_status_enum")

"""Per-user research topics; remove admin role.

Revision ID: 007
Revises: 006
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "research_topics",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_research_topics_user_id", "research_topics", ["user_id"])
    op.create_foreign_key(
        "fk_research_topics_user_id",
        "research_topics",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.execute(
        """
        UPDATE research_topics
        SET user_id = (
            SELECT id FROM users WHERE is_active = true ORDER BY created_at LIMIT 1
        )
        WHERE user_id IS NULL
        """
    )
    op.execute("DELETE FROM research_topics WHERE user_id IS NULL")
    op.alter_column("research_topics", "user_id", nullable=False)

    op.drop_column("users", "role")
    op.execute("DROP TYPE IF EXISTS user_role_enum")


def downgrade() -> None:
    op.execute("CREATE TYPE user_role_enum AS ENUM ('admin', 'user')")
    op.add_column(
        "users",
        sa.Column(
            "role",
            postgresql.ENUM("admin", "user", name="user_role_enum", create_type=False),
            nullable=False,
            server_default="user",
        ),
    )
    op.execute(
        """
        UPDATE users SET role = 'admin'
        WHERE id = (SELECT id FROM users ORDER BY created_at LIMIT 1)
        """
    )

    op.drop_constraint("fk_research_topics_user_id", "research_topics", type_="foreignkey")
    op.drop_index("ix_research_topics_user_id", table_name="research_topics")
    op.drop_column("research_topics", "user_id")

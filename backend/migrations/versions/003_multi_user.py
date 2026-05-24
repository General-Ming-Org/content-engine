"""Multi-user portal: users, user_credentials, and user_id on existing tables.

Revision ID: 003
Revises: 002
Create Date: 2026-05-23 00:00:00.000000

Strategy for existing data:
    If any rows exist in posts/articles/etc, the migration creates a placeholder
    admin user ("legacy@content-engine.local") with a random password, and
    backfills all existing rows to that user_id. Operator should then signup as
    themselves (which becomes regular user since admin already exists), reassign
    rows manually, and delete the placeholder.

    Fresh installs skip the placeholder — the first signup becomes admin.
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PLACEHOLDER_EMAIL = "legacy@content-engine.local"


def upgrade() -> None:
    # ── Enum + users ──────────────────────────────────────────────────────────
    op.execute("CREATE TYPE user_role_enum AS ENUM ('admin', 'user')")
    op.execute("""
        CREATE TYPE credential_provider_enum AS ENUM
        ('linkedin', 'linkedin_app', 'substack', 'smtp', 'mcp_token')
    """)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column(
            "role",
            postgresql.ENUM("admin", "user", name="user_role_enum", create_type=False),
            nullable=False,
            server_default="user",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "user_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "provider",
            postgresql.ENUM(
                "linkedin", "linkedin_app", "substack", "smtp", "mcp_token",
                name="credential_provider_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("secret_payload", sa.Text(), nullable=True),
        sa.Column("metadata_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_credentials"),
    )
    op.create_index("ix_user_credentials_user_id", "user_credentials", ["user_id"])

    # ── Placeholder for backfill if existing data exists ──────────────────────
    bind = op.get_bind()
    needs_backfill = False
    for table in ("posts", "articles", "engagement_actions", "metric_snapshots",
                  "strategy_reports", "goals", "notifications", "user_settings",
                  "embedding_records"):
        try:
            count = bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()
            if count and count > 0:
                needs_backfill = True
                break
        except Exception:
            pass

    placeholder_id: uuid.UUID | None = None
    if needs_backfill:
        placeholder_id = uuid.uuid4()
        # bcrypt hash of a random throwaway — operator must signup separately to use the system
        bind.execute(sa.text("""
            INSERT INTO users (id, email, password_hash, name, role, is_active)
            VALUES (:id, :email, :pw, 'Legacy data owner', 'admin', false)
        """), {
            "id": str(placeholder_id),
            "email": PLACEHOLDER_EMAIL,
            "pw": "!disabled_placeholder_no_login!",
        })

    # ── Add user_id to existing tables ────────────────────────────────────────
    for table, nullable in [
        ("posts", False),
        ("articles", False),
        ("engagement_actions", False),
        ("metric_snapshots", False),
        ("strategy_reports", False),
        ("goals", False),
        ("notifications", False),
        ("embedding_records", True),  # research kind has null user_id
    ]:
        op.add_column(
            table,
            sa.Column(
                "user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=True,  # added nullable, backfilled, then set NOT NULL below
            ),
        )
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])

        if placeholder_id and not nullable:
            bind.execute(sa.text(f"UPDATE {table} SET user_id = :uid WHERE user_id IS NULL"),
                         {"uid": str(placeholder_id)})
        if not nullable:
            op.alter_column(table, "user_id", nullable=False)

    # ── user_settings: drop old PK, add id + user_id, new unique constraint ───
    op.drop_constraint("user_settings_pkey", "user_settings", type_="primary")
    op.add_column("user_settings", sa.Column("id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("user_settings", sa.Column(
        "user_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True,
    ))
    bind.execute(sa.text("UPDATE user_settings SET id = gen_random_uuid() WHERE id IS NULL"))
    if placeholder_id:
        bind.execute(sa.text("UPDATE user_settings SET user_id = :uid WHERE user_id IS NULL"),
                     {"uid": str(placeholder_id)})
    op.alter_column("user_settings", "id", nullable=False)
    op.alter_column("user_settings", "user_id", nullable=False)
    op.create_primary_key("user_settings_pkey", "user_settings", ["id"])
    op.create_index("ix_user_settings_user_id", "user_settings", ["user_id"])
    op.create_unique_constraint("uq_user_settings", "user_settings", ["user_id", "key"])


def downgrade() -> None:
    op.drop_constraint("uq_user_settings", "user_settings", type_="unique")
    op.drop_index("ix_user_settings_user_id", table_name="user_settings")
    op.drop_constraint("user_settings_pkey", "user_settings", type_="primary")
    op.drop_column("user_settings", "user_id")
    op.drop_column("user_settings", "id")
    op.create_primary_key("user_settings_pkey", "user_settings", ["key"])

    for table in ("embedding_records", "notifications", "goals", "strategy_reports",
                  "metric_snapshots", "engagement_actions", "articles", "posts"):
        op.drop_index(f"ix_{table}_user_id", table_name=table)
        op.drop_column(table, "user_id")

    op.drop_index("ix_user_credentials_user_id", table_name="user_credentials")
    op.drop_table("user_credentials")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.execute("DROP TYPE credential_provider_enum")
    op.execute("DROP TYPE user_role_enum")

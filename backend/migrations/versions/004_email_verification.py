"""Email verification + name now required

Revision ID: 004
Revises: 003
Create Date: 2026-05-24 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("email_verification_token_hash", sa.Text(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("email_verification_sent_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Backfill name for any existing rows so the NOT NULL constraint can be
    # applied. Pre-existing accounts (including the legacy seed user) get a
    # placeholder derived from their email local-part.
    op.execute(
        "UPDATE users SET name = split_part(email, '@', 1) WHERE name IS NULL OR name = ''"
    )
    op.alter_column("users", "name", existing_type=sa.Text(), nullable=False)

    # Mark all pre-existing accounts as already verified — we don't want to
    # retroactively force verification on people who signed up before the
    # feature shipped.
    op.execute("UPDATE users SET email_verified_at = NOW() WHERE email_verified_at IS NULL")


def downgrade() -> None:
    op.alter_column("users", "name", existing_type=sa.Text(), nullable=True)
    op.drop_column("users", "email_verification_sent_at")
    op.drop_column("users", "email_verification_token_hash")
    op.drop_column("users", "email_verified_at")

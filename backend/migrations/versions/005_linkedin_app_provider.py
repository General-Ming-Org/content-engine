"""Add linkedin_app to credential_provider_enum

Revision ID: 005
Revises: 004
Create Date: 2026-05-24

Per-user LinkedIn Developer App (Client ID / Secret) stored under provider linkedin_app.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL 15+ supports IF NOT EXISTS; safe on re-run.
    op.execute(
        "ALTER TYPE credential_provider_enum ADD VALUE IF NOT EXISTS 'linkedin_app'"
    )


def downgrade() -> None:
    # Postgres cannot drop enum values easily; no-op downgrade.
    pass

"""Profiles: a username, display name, bio and profile picture per account.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("username", sa.String(20), unique=True),
        sa.Column("display_name", sa.String(50)),
        sa.Column("bio", sa.String(300)),
        sa.Column("avatar_key", sa.String(255)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("profiles")

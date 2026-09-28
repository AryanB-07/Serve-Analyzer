"""Login and signup attempts, for rate limits shared by every API process.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_attempts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("auth_attempts_key_at", "auth_attempts", ["key_hash", "at"])


def downgrade() -> None:
    op.drop_table("auth_attempts")

"""Time-limited job claims: claim token, heartbeat and attempt count.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("analyses") as batch:
        batch.add_column(sa.Column("claim_token", sa.String(32)))
        batch.add_column(sa.Column("heartbeat_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("attempts", sa.Integer, nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("analyses") as batch:
        batch.drop_column("attempts")
        batch.drop_column("heartbeat_at")
        batch.drop_column("claim_token")

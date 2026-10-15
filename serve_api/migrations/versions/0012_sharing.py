"""What friends may see: serve stats, per-position averages, and a place on the leaderboard.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

COLUMNS = ("share_stats", "share_positions", "on_leaderboard")


def upgrade() -> None:
    with op.batch_alter_table("profiles") as batch:
        for name in COLUMNS:
            batch.add_column(sa.Column(name, sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("profiles") as batch:
        for name in COLUMNS:
            batch.drop_column(name)

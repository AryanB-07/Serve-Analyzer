"""Friends: requests and friendships, blocks, and who can send you a request.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("profiles") as batch:
        batch.add_column(sa.Column("accept_requests", sa.Boolean, nullable=False, server_default=sa.true()))
    op.create_table(
        "connections",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("requester_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("addressee_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pair", sa.String(65), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("connections_addressee", "connections", ["addressee_id", "status"])
    op.create_index("connections_requester", "connections", ["requester_id", "status"])
    op.create_table(
        "blocks",
        sa.Column("blocker_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("blocked_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("blocks_blocked", "blocks", ["blocked_id"])


def downgrade() -> None:
    op.drop_table("blocks")
    op.drop_table("connections")
    with op.batch_alter_table("profiles") as batch:
        batch.drop_column("accept_requests")

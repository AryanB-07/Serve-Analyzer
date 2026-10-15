"""Notifications, usernames held after they're released, and suspending accounts.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("suspended_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("suspended_reason", sa.Text))
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", sa.String(32), sa.ForeignKey("conversations.id", ondelete="CASCADE")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
    )
    op.create_index("notifications_user", "notifications", ["user_id", "created_at"])
    op.create_index("notifications_actor", "notifications", ["actor_id"])
    op.create_table(
        "released_usernames",
        sa.Column("username", sa.String(20), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("released_usernames")
    op.drop_table("notifications")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("suspended_reason")
        batch.drop_column("suspended_at")

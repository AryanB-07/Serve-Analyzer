"""Messages between friends, and reports of people and messages.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("pair", sa.String(65), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "conversation_members",
        sa.Column("conversation_id", sa.String(32), sa.ForeignKey("conversations.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("last_read_at", sa.DateTime(timezone=True)),
    )
    op.create_index("conversation_members_user", "conversation_members", ["user_id"])
    op.create_table(
        "messages",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("conversation_id", sa.String(32), sa.ForeignKey("conversations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("sender_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("body", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("messages_conversation", "messages", ["conversation_id", "created_at"])
    op.create_index("messages_sender", "messages", ["sender_id"])
    op.create_table(
        "user_reports",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("reporter_id", sa.String(32), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reported_id", sa.String(32), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reported_username", sa.String(20)),
        sa.Column("message_id", sa.String(32)),
        sa.Column("message_body", sa.Text),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("user_reports_created", "user_reports", ["created_at"])


def downgrade() -> None:
    op.drop_table("user_reports")
    op.drop_table("messages")
    op.drop_table("conversation_members")
    op.drop_table("conversations")

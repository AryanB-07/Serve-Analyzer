"""Serves sent in messages: a message can carry one of the sender's analyses.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.add_column(sa.Column("analysis_id", sa.String(32)))
        batch.create_foreign_key("fk_messages_analysis", "analyses", ["analysis_id"], ["id"], ondelete="SET NULL")
    op.create_index("messages_analysis", "messages", ["analysis_id"])


def downgrade() -> None:
    op.drop_index("messages_analysis", "messages")
    with op.batch_alter_table("messages") as batch:
        batch.drop_constraint("fk_messages_analysis", type_="foreignkey")
        batch.drop_column("analysis_id")

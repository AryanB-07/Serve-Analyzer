"""Reports that a result looks wrong, and the new address in an email-change link.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("email_tokens") as batch:
        batch.add_column(sa.Column("new_email", sa.String(320)))
    op.create_table(
        "result_reports",
        sa.Column("analysis_id", sa.String(32), sa.ForeignKey("analyses.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("note", sa.Text),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_result_reports_user_id", "result_reports", ["user_id"])
    op.create_index("result_reports_created", "result_reports", ["created_at"])


def downgrade() -> None:
    op.drop_index("result_reports_created", "result_reports")
    op.drop_index("ix_result_reports_user_id", "result_reports")
    op.drop_table("result_reports")
    with op.batch_alter_table("email_tokens") as batch:
        batch.drop_column("new_email")

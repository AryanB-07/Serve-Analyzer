"""History: each analysis's overall and key-position scores, and the person's note.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("analyses") as batch:
        batch.add_column(sa.Column("overall_score", sa.Integer))
        batch.add_column(sa.Column("key_scores", sa.JSON().with_variant(JSONB(), "postgresql")))
        batch.add_column(sa.Column("note", sa.Text))
    op.create_index("analyses_user_score", "analyses", ["user_id", "overall_score"])


def downgrade() -> None:
    op.drop_index("analyses_user_score", "analyses")
    with op.batch_alter_table("analyses") as batch:
        batch.drop_column("note")
        batch.drop_column("key_scores")
        batch.drop_column("overall_score")

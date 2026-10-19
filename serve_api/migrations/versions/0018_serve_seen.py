"""When the recipient first opened the serve sent in a message, for the Received view.

Serves sent before this have no record of being opened, so they start unseen.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.add_column(sa.Column("seen_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.drop_column("seen_at")

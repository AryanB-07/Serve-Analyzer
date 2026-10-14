"""Where the person said the camera was, asked at upload.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("analyses") as batch:
        batch.add_column(sa.Column("camera_view", sa.String(32)))


def downgrade() -> None:
    with op.batch_alter_table("analyses") as batch:
        batch.drop_column("camera_view")

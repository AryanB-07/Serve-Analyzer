"""Baseline: the analyses table (also the job queue).

Databases created before migrations existed (SQLite, text timestamps and JSON)
are converted in place.

Revision ID: 0001
Revises:
Create Date: 2026-09-27
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _create_analyses() -> sa.Table:
    table = op.create_table(
        "analyses",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("hand", sa.String(8), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.Text),
        sa.Column("counts", sa.JSON().with_variant(JSONB(), "postgresql")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("analyses_status", "analyses", ["status", "updated_at"])
    op.create_index("analyses_created", "analyses", ["created_at", "id"])
    return table


def _utc_naive(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(UTC).replace(tzinfo=None)


def upgrade() -> None:
    legacy = sa.inspect(op.get_bind()).has_table("analyses")
    if legacy:
        op.drop_index("analyses_status", "analyses")
        op.drop_index("analyses_created", "analyses")
        op.rename_table("analyses", "analyses_legacy")
    table = _create_analyses()
    if legacy:
        rows = op.get_bind().execute(sa.text("SELECT * FROM analyses_legacy")).mappings().all()
        op.bulk_insert(table, [
            {**row, "counts": json.loads(row["counts"]) if row["counts"] else None,
             "created_at": _utc_naive(row["created_at"]), "updated_at": _utc_naive(row["updated_at"])}
            for row in rows
        ])
        op.drop_table("analyses_legacy")


def downgrade() -> None:
    op.drop_table("analyses")

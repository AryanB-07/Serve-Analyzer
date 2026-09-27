"""Database schema. Any change here needs a matching Alembic migration in migrations/versions."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, BigInteger, Column, DateTime, Index, MetaData, String, Table, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """Timezone-aware UTC datetimes on every backend (SQLite stores them without an offset)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is not None and dialect.name == "sqlite":
            return value.astimezone(UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


JSONType = JSON().with_variant(JSONB(), "postgresql")

metadata = MetaData()

analyses = Table(
    "analyses",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("hand", String(8), nullable=False),
    Column("filename", String(255), nullable=False),
    Column("content_type", String(64), nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    # Also the job queue: awaiting_upload -> queued -> extracting_pose/analyzing/rendering
    # -> succeeded | failed.
    Column("status", String(32), nullable=False),
    Column("error_code", String(64)),
    Column("error_message", Text),
    Column("counts", JSONType),
    Column("created_at", UTCDateTime, nullable=False),
    Column("updated_at", UTCDateTime, nullable=False),
    Index("analyses_status", "status", "updated_at"),
    Index("analyses_created", "created_at", "id"),
)

"""Database schema. Any change here needs a matching Alembic migration in migrations/versions."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    String,
    Table,
    Text,
)
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
    Column("user_id", String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
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
    Index("analyses_user_created", "user_id", "created_at", "id"),  # a user's History page
)

users = Table(
    "users",
    metadata,
    Column("id", String(32), primary_key=True),
    # Stored lower-cased, so the unique index is case-insensitive on every backend.
    Column("email", String(320), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("created_at", UTCDateTime, nullable=False),
)

sessions = Table(
    "sessions",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("user_id", String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
           index=True),
    # SHA-256 of the cookie token; the token itself is never stored.
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("created_at", UTCDateTime, nullable=False),
    Column("expires_at", UTCDateTime, nullable=False),
    Column("last_seen_at", UTCDateTime, nullable=False),
)

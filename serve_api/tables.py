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
    Integer,
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
    # Job claims. A worker holds a job while it keeps heartbeat_at fresh; its writes
    # only count while claim_token is still its own. attempts counts claims so far.
    Column("claim_token", String(32)),
    Column("heartbeat_at", UTCDateTime),
    Column("attempts", Integer, nullable=False, server_default="0"),
    # When the original upload was deleted under the retention policy (results are kept).
    Column("input_deleted_at", UTCDateTime),
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
    Column("email_verified_at", UTCDateTime),
    # Which version of the Terms and Privacy Policy the person agreed to at signup, and when.
    Column("terms_version", String(32)),
    Column("terms_accepted_at", UTCDateTime),
)

email_tokens = Table(
    "email_tokens",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("user_id", String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
           index=True),
    Column("purpose", String(16), nullable=False),  # "verify" | "reset"
    # SHA-256 of the token in the emailed link; the token itself is never stored.
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("created_at", UTCDateTime, nullable=False),
    Column("expires_at", UTCDateTime, nullable=False),
    Column("used_at", UTCDateTime),
)

storage_purges = Table(
    "storage_purges",
    metadata,
    # Storage prefixes still to delete after an analysis or account was deleted. Written in
    # the same transaction as the deletion and cleared once the files are gone, so a storage
    # outage can delay a deletion but never lose it.
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("prefix", String(255), nullable=False),
    Column("created_at", UTCDateTime, nullable=False),
)

auth_attempts = Table(
    "auth_attempts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    # SHA-256 of "scope:key" (an IP, or an email), so no addresses are stored.
    Column("key_hash", String(64), nullable=False),
    Column("at", UTCDateTime, nullable=False),
    Index("auth_attempts_key_at", "key_hash", "at"),
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

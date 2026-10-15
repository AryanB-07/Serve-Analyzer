"""Database schema. Any change here needs a matching Alembic migration in migrations/versions."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
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
from sqlalchemy import true
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
    # Where the person said the camera was (schemas.CameraView), or null.
    Column("camera_view", String(32)),
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
    # For History: the overall score and the key positions' scores (serve_analyzer.score), copied
    # from results.json when the analysis succeeds, and the person's own note.
    Column("overall_score", Integer),
    Column("key_scores", JSONType),
    Column("note", Text),
    Index("analyses_status", "status", "updated_at"),
    Index("analyses_user_created", "user_id", "created_at", "id"),  # a user's History page
    Index("analyses_user_score", "user_id", "overall_score"),       # filtered by score
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

profiles = Table(
    "profiles",
    metadata,
    # The public side of an account (shown to other people once social features exist). A row
    # appears the first time someone sets anything; until then the account has the defaults.
    Column("user_id", String(32), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    # Stored lower-cased, so the unique index is case-insensitive on every backend.
    Column("username", String(20), unique=True),
    Column("display_name", String(50)),
    Column("bio", String(300)),
    # Storage key of the current profile picture (keys.avatar_key), or none.
    Column("avatar_key", String(255)),
    Column("updated_at", UTCDateTime, nullable=False),
    # Privacy: whether anyone who knows your username can send you a friend request.
    Column("accept_requests", Boolean, nullable=False, server_default=true()),
)

connections = Table(
    "connections",
    metadata,
    # A friend request, and once accepted, a friendship. One per pair of people, whichever of
    # them asked: `pair` is both ids in sorted order, under a unique index.
    Column("id", String(32), primary_key=True),
    Column("requester_id", String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("addressee_id", String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("pair", String(65), nullable=False, unique=True),
    Column("status", String(16), nullable=False),  # "pending" | "accepted"
    Column("created_at", UTCDateTime, nullable=False),
    Column("accepted_at", UTCDateTime),
    Index("connections_addressee", "addressee_id", "status"),
    Index("connections_requester", "requester_id", "status"),
)

blocks = Table(
    "blocks",
    metadata,
    # The blocked person can't find, request or see the blocker, and isn't told.
    Column("blocker_id", String(32), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("blocked_id", String(32), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", UTCDateTime, nullable=False),
    Index("blocks_blocked", "blocked_id"),
)

email_tokens = Table(
    "email_tokens",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("user_id", String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
           index=True),
    Column("purpose", String(16), nullable=False),  # "verify" | "reset" | "email_change"
    # SHA-256 of the token in the emailed link; the token itself is never stored.
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("created_at", UTCDateTime, nullable=False),
    Column("expires_at", UTCDateTime, nullable=False),
    Column("used_at", UTCDateTime),
    # For "email_change": the address the link was sent to, which becomes the account's email.
    Column("new_email", String(320)),
)

result_reports = Table(
    "result_reports",
    metadata,
    # "This result looks wrong": at most one per analysis (a new report replaces the old one),
    # deleted with the analysis. Labels for finding the pipeline's mistakes. (Training a model on
    # the clips would need the Privacy Policy changed first: it says videos aren't used for that.)
    Column("analysis_id", String(32), ForeignKey("analyses.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
           index=True),
    Column("reason", String(32), nullable=False),
    Column("note", Text),
    # The analysis's status and error code when it was reported.
    Column("status", String(32), nullable=False),
    Column("error_code", String(64)),
    Column("created_at", UTCDateTime, nullable=False),
    Index("result_reports_created", "created_at"),
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

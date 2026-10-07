"""Persistence (SQLite or Postgres): analyses, which double as the job queue, users, sessions,
emailed tokens and the storage purge queue."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import (
    Connection,
    Engine,
    create_engine,
    delete,
    event,
    func,
    insert,
    select,
    tuple_,
    update,
)
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from .tables import analyses, auth_attempts, email_tokens, sessions, storage_purges, users

IN_PROGRESS = ("extracting_pose", "analyzing", "rendering")
ACTIVE = ("queued", *IN_PROGRESS)


def now() -> datetime:
    return datetime.now(UTC)


def make_engine(url: str) -> Engine:
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite":
        return create_engine(url, pool_pre_ping=True)
    if parsed.database and parsed.database != ":memory:":
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    # FastAPI runs sync endpoints in a thread pool, so connections cross threads.
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 10})

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return engine


class Database:
    def __init__(self, url_or_engine: str | Engine) -> None:
        self.engine = (
            url_or_engine if isinstance(url_or_engine, Engine) else make_engine(url_or_engine)
        )

    @contextmanager
    def _locked_for(self, user_id: str) -> Iterator[Connection]:
        """A transaction that holds a lock for ``user_id`` until it commits.

        Check-then-write sequences (count this user's analyses, then add one)
        run inside it, so two concurrent requests from the same user can't both
        pass the check. Postgres locks the user's row, so other users aren't
        blocked; SQLite has no row locks and takes its database write lock.
        """
        with self.engine.connect() as conn:
            if conn.dialect.name == "sqlite":
                conn.exec_driver_sql("BEGIN IMMEDIATE")
            else:
                conn.execute(select(users.c.id).where(users.c.id == user_id).with_for_update())
            try:
                yield conn
            except BaseException:
                conn.rollback()
                raise
            conn.commit()

    def create_within_limit(
        self, user_id: str, hand: str, filename: str, content_type: str, size_bytes: int,
        since: datetime, limit: int,
    ) -> dict[str, Any] | None:
        """Create an analysis unless the user already created ``limit`` since ``since``."""
        with self._locked_for(user_id) as conn:
            if self._count_created_since(conn, user_id, since) >= limit:
                return None
            return self._insert(conn, user_id, hand, filename, content_type, size_bytes)

    def transition_within_limit(
        self, analysis_id: str, user_id: str, from_statuses: tuple[str, ...], to_status: str,
        max_active: int, **fields: Any,
    ) -> Literal["ok", "limit", "conflict"]:
        """Queue an analysis unless the user already has ``max_active`` queued or running."""
        with self._locked_for(user_id) as conn:
            current = conn.execute(
                select(analyses.c.status).where(analyses.c.id == analysis_id)).scalar_one_or_none()
            if current not in from_statuses:
                return "conflict"
            if self._count_active(conn, user_id) >= max_active:
                return "limit"
            self._transition(conn, analysis_id, from_statuses, to_status, **fields)
            return "ok"

    def create(
        self, user_id: str, hand: str, filename: str, content_type: str, size_bytes: int
    ) -> dict[str, Any]:
        with self.engine.begin() as conn:
            return self._insert(conn, user_id, hand, filename, content_type, size_bytes)

    def _insert(
        self, conn: Connection, user_id: str, hand: str, filename: str, content_type: str,
        size_bytes: int,
    ) -> dict[str, Any]:
        ts = now()
        row = {
            "id": uuid.uuid4().hex, "user_id": user_id, "hand": hand, "filename": filename,
            "content_type": content_type, "size_bytes": size_bytes,
            "status": "awaiting_upload", "error_code": None, "error_message": None,
            "counts": None, "created_at": ts, "updated_at": ts,
            "claim_token": None, "heartbeat_at": None, "attempts": 0, "input_deleted_at": None,
        }
        conn.execute(insert(analyses).values(row))
        return row

    def get(self, analysis_id: str) -> dict[str, Any] | None:
        """Any user's analysis. For the worker and internal checks; API routes use get_owned."""
        with self.engine.connect() as conn:
            row = conn.execute(select(analyses).where(analyses.c.id == analysis_id)).mappings().first()
        return dict(row) if row else None

    def get_owned(self, analysis_id: str, user_id: str) -> dict[str, Any] | None:
        """The analysis if it belongs to ``user_id``; None if it doesn't exist or isn't theirs."""
        query = select(analyses).where(analyses.c.id == analysis_id, analyses.c.user_id == user_id)
        with self.engine.connect() as conn:
            row = conn.execute(query).mappings().first()
        return dict(row) if row else None

    def list(
        self, user_id: str, limit: int, before: tuple[datetime, str] | None = None
    ) -> list[dict[str, Any]]:
        """A user's analyses, newest first. ``before`` is a (created_at, id) keyset cursor."""
        query = select(analyses).where(analyses.c.user_id == user_id)
        if before:
            query = query.where(tuple_(analyses.c.created_at, analyses.c.id) < tuple_(*before))
        query = query.order_by(analyses.c.created_at.desc(), analyses.c.id.desc()).limit(limit)
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(query).mappings()]

    def transition(
        self, analysis_id: str, from_statuses: tuple[str, ...], to_status: str, **fields: Any
    ) -> bool:
        """Atomically move to ``to_status`` only if currently in ``from_statuses``."""
        with self.engine.begin() as conn:
            return self._transition(conn, analysis_id, from_statuses, to_status, **fields)

    @staticmethod
    def _transition(
        conn: Connection, analysis_id: str, from_statuses: tuple[str, ...], to_status: str,
        **fields: Any,
    ) -> bool:
        result = conn.execute(
            update(analyses)
            .where(analyses.c.id == analysis_id, analyses.c.status.in_(from_statuses))
            .values(status=to_status, error_code=None, error_message=None, updated_at=now(),
                    **fields)
        )
        return result.rowcount == 1

    def set_status(self, analysis_id: str, status: str, **fields: Any) -> None:
        """Unconditional status write, for tests and maintenance. Workers use update_claimed."""
        with self.engine.begin() as conn:
            conn.execute(
                update(analyses).where(analyses.c.id == analysis_id)
                .values(status=status, updated_at=now(), **fields)
            )

    # --- the job queue ---------------------------------------------------------

    def claim_next(self, token: str) -> dict[str, Any] | None:
        """Take the oldest queued job, marking it with the worker's claim ``token``.

        One UPDATE makes the claim atomic. On Postgres, SKIP LOCKED lets
        concurrent workers pass over a row another worker is claiming instead
        of waiting for it; SQLite serialises writers, so it needs neither.
        """
        oldest = (
            select(analyses.c.id).where(analyses.c.status == "queued")
            .order_by(analyses.c.updated_at).limit(1)
            .with_for_update(skip_locked=True).scalar_subquery()
        )
        ts = now()
        with self.engine.begin() as conn:
            row = conn.execute(
                update(analyses).where(analyses.c.id == oldest)
                .values(status=IN_PROGRESS[0], claim_token=token, heartbeat_at=ts,
                        attempts=analyses.c.attempts + 1, updated_at=ts)
                .returning(*analyses.c)
            ).mappings().first()
        return dict(row) if row else None

    def _claimed(self, analysis_id: str, token: str):
        return (analyses.c.id == analysis_id, analyses.c.claim_token == token,
                analyses.c.status.in_(IN_PROGRESS))

    def update_claimed(self, analysis_id: str, token: str, status: str, **fields: Any) -> bool:
        """A worker's status write. Returns False, changing nothing, if the job is no
        longer claimed with ``token`` (the claim lapsed and the job moved on)."""
        ts = now()
        if status not in IN_PROGRESS:
            fields["claim_token"] = None
        with self.engine.begin() as conn:
            result = conn.execute(
                update(analyses).where(*self._claimed(analysis_id, token))
                .values(status=status, updated_at=ts, heartbeat_at=ts, **fields)
            )
        return result.rowcount == 1

    def heartbeat(self, analysis_id: str, token: str) -> bool:
        """Keep a claim alive. False if it has already lapsed."""
        with self.engine.begin() as conn:
            result = conn.execute(
                update(analyses).where(*self._claimed(analysis_id, token))
                .values(heartbeat_at=now())
            )
        return result.rowcount == 1

    def release_stale(
        self, lease: timedelta, max_attempts: int, failure_message: str
    ) -> tuple[int, int]:
        """Return abandoned jobs (no heartbeat for ``lease``) to the queue.

        A job that has already been claimed ``max_attempts`` times is failed
        instead, so a video that crashes workers can't loop forever.
        Returns (requeued, failed).
        """
        stale = (analyses.c.status.in_(IN_PROGRESS),
                 (analyses.c.heartbeat_at < now() - lease) | analyses.c.heartbeat_at.is_(None))
        with self.engine.begin() as conn:
            failed = conn.execute(
                update(analyses).where(*stale, analyses.c.attempts >= max_attempts)
                .values(status="failed", error_code="INTERNAL", error_message=failure_message,
                        claim_token=None, updated_at=now())
            ).rowcount
            requeued = conn.execute(
                update(analyses).where(*stale)
                .values(status="queued", claim_token=None, updated_at=now())
            ).rowcount
        return requeued, failed

    def queue_stats(self) -> dict[str, Any]:
        """For monitoring: jobs waiting and running, and how long the oldest has waited."""
        with self.engine.connect() as conn:
            queued, oldest = conn.execute(
                select(func.count(), func.min(analyses.c.updated_at)).where(analyses.c.status == "queued")
            ).one()
            running = conn.execute(select(func.count()).select_from(analyses).where(
                analyses.c.status.in_(IN_PROGRESS))).scalar_one()
        if oldest is not None and oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=UTC)  # min() comes back untyped on SQLite
        waited = (now() - oldest).total_seconds() if oldest is not None else 0.0
        return {"queued": queued, "running": running, "oldest_queued_s": round(waited)}

    # --- per-user limits ---------------------------------------------------------

    @staticmethod
    def _count_created_since(conn: Connection, user_id: str, since: datetime) -> int:
        return conn.execute(select(func.count()).select_from(analyses).where(
            analyses.c.user_id == user_id, analyses.c.created_at >= since)).scalar_one()

    @staticmethod
    def _count_active(conn: Connection, user_id: str) -> int:
        """Analyses waiting in the queue or being processed."""
        return conn.execute(select(func.count()).select_from(analyses).where(
            analyses.c.user_id == user_id, analyses.c.status.in_(ACTIVE))).scalar_one()

    # --- users and sessions ----------------------------------------------------

    def create_user(self, email: str, password_hash: str,
                    terms_version: str | None = None) -> dict[str, Any] | None:
        """Returns None if the email is already registered. ``email`` must be normalised.
        ``terms_version`` records the Terms and Privacy Policy accepted at signup."""
        ts = now()
        row = {"id": uuid.uuid4().hex, "email": email, "password_hash": password_hash,
               "created_at": ts, "email_verified_at": None, "terms_version": terms_version,
               "terms_accepted_at": ts if terms_version else None}
        try:
            with self.engine.begin() as conn:
                conn.execute(insert(users).values(row))
        except IntegrityError:
            return None
        return row

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(users).where(users.c.email == email)).mappings().first()
        return dict(row) if row else None

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(users).where(users.c.id == user_id)).mappings().first()
        return dict(row) if row else None

    def mark_email_verified(self, user_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(users).where(users.c.id == user_id, users.c.email_verified_at.is_(None))
                         .values(email_verified_at=now()))

    def reset_password(self, user_id: str, password_hash: str) -> None:
        """Set a new password, sign out every session, and void outstanding reset links.

        Following a reset link proves control of the inbox, so the email counts as verified.
        """
        ts = now()
        with self.engine.begin() as conn:
            conn.execute(update(users).where(users.c.id == user_id).values(password_hash=password_hash))
            conn.execute(update(users).where(users.c.id == user_id, users.c.email_verified_at.is_(None))
                         .values(email_verified_at=ts))
            conn.execute(delete(sessions).where(sessions.c.user_id == user_id))
            conn.execute(delete(email_tokens).where(email_tokens.c.user_id == user_id,
                                                    email_tokens.c.purpose == "reset"))

    # --- emailed tokens --------------------------------------------------------

    def create_email_token(self, user_id: str, purpose: str, token_hash: str,
                           expires_at: datetime) -> None:
        """Store a new link token. Earlier unused tokens for the same purpose stop working,
        so only the most recent email's link is valid."""
        with self.engine.begin() as conn:
            conn.execute(delete(email_tokens).where(
                email_tokens.c.user_id == user_id, email_tokens.c.purpose == purpose,
                email_tokens.c.used_at.is_(None)))
            conn.execute(insert(email_tokens).values(
                id=uuid.uuid4().hex, user_id=user_id, purpose=purpose, token_hash=token_hash,
                created_at=now(), expires_at=expires_at, used_at=None))

    def use_email_token(self, token_hash: str, purpose: str) -> str | None:
        """Spend a token: returns its user id, or None if it's unknown, used or expired.

        One UPDATE makes it single-use even when two requests race."""
        with self.engine.begin() as conn:
            row = conn.execute(
                update(email_tokens)
                .where(email_tokens.c.token_hash == token_hash, email_tokens.c.purpose == purpose,
                       email_tokens.c.used_at.is_(None), email_tokens.c.expires_at > now())
                .values(used_at=now())
                .returning(email_tokens.c.user_id)
            ).first()
        return row[0] if row else None

    # --- deletion ----------------------------------------------------------------

    @staticmethod
    def _queue_purges(conn: Connection, prefixes: list[str]) -> list[int]:
        ts = now()
        return [conn.execute(insert(storage_purges).values(prefix=p, created_at=ts)).inserted_primary_key[0]
                for p in prefixes]

    def delete_analysis(self, analysis_id: str, user_id: str, prefixes: list[str]) -> list[int] | None:
        """Delete one of ``user_id``'s analyses and queue its storage ``prefixes`` for removal,
        in one transaction. Returns the purge ids, or None if there was no such analysis."""
        with self.engine.begin() as conn:
            gone = conn.execute(delete(analyses).where(
                analyses.c.id == analysis_id, analyses.c.user_id == user_id)).rowcount
            return self._queue_purges(conn, prefixes) if gone else None

    def delete_user(self, user_id: str, prefixes_for: Any) -> list[int]:
        """Delete an account with its sessions, tokens and analyses, queueing every analysis's
        storage (``prefixes_for(analysis_id)``) for removal. Returns the purge ids."""
        with self.engine.begin() as conn:
            ids = list(conn.execute(select(analyses.c.id).where(analyses.c.user_id == user_id)).scalars())
            purge_ids = self._queue_purges(conn, [p for i in ids for p in prefixes_for(i)])
            # Explicit deletes rather than relying on ON DELETE CASCADE alone.
            for table in (analyses, sessions, email_tokens):
                conn.execute(delete(table).where(table.c.user_id == user_id))
            conn.execute(delete(users).where(users.c.id == user_id))
        return purge_ids

    def pending_purges(self, ids: list[int] | None = None) -> list[tuple[int, str]]:
        query = select(storage_purges.c.id, storage_purges.c.prefix).order_by(storage_purges.c.id)
        if ids is not None:
            query = query.where(storage_purges.c.id.in_(ids))
        with self.engine.connect() as conn:
            return [(r[0], r[1]) for r in conn.execute(query)]

    def finish_purge(self, purge_id: int) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(storage_purges).where(storage_purges.c.id == purge_id))

    def set_password_hash(self, user_id: str, password_hash: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(users).where(users.c.id == user_id).values(password_hash=password_hash))

    def create_session(self, user_id: str, token_hash: str, expires_at: datetime) -> None:
        ts = now()
        with self.engine.begin() as conn:
            # Housekeeping: a login is a natural moment to drop this user's dead sessions.
            conn.execute(delete(sessions).where(sessions.c.user_id == user_id,
                                                sessions.c.expires_at < ts))
            conn.execute(insert(sessions).values(
                id=uuid.uuid4().hex, user_id=user_id, token_hash=token_hash,
                created_at=ts, expires_at=expires_at, last_seen_at=ts,
            ))

    def get_session(self, token_hash: str) -> dict[str, Any] | None:
        """The live session for a token, joined with its user (``user_*`` keys), or None."""
        query = (
            select(sessions, users.c.email.label("user_email"),
                   users.c.created_at.label("user_created_at"),
                   users.c.email_verified_at.label("user_email_verified_at"))
            .join(users, users.c.id == sessions.c.user_id)
            .where(sessions.c.token_hash == token_hash, sessions.c.expires_at > now())
        )
        with self.engine.connect() as conn:
            row = conn.execute(query).mappings().first()
        return dict(row) if row else None

    def extend_session(self, session_id: str, expires_at: datetime) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(sessions).where(sessions.c.id == session_id)
                         .values(expires_at=expires_at, last_seen_at=now()))

    # --- rate limiting and housekeeping ------------------------------------------

    def record_attempt(self, key_hash: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(insert(auth_attempts).values(key_hash=key_hash, at=now()))

    def attempts_since(self, key_hash: str, since: datetime) -> tuple[int, datetime | None]:
        """How many attempts for ``key_hash`` since ``since``, and the oldest of them."""
        query = select(func.count(), func.min(auth_attempts.c.at)).where(
            auth_attempts.c.key_hash == key_hash, auth_attempts.c.at > since)
        with self.engine.connect() as conn:
            count, oldest = conn.execute(query).one()
        if oldest is not None and oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=UTC)  # min() comes back untyped on SQLite
        return count, oldest

    def delete_expired(self, attempts_before: datetime) -> tuple[int, int]:
        """Drop expired sessions, emailed tokens and old rate-limit rows.
        Returns how many sessions and attempts were removed."""
        with self.engine.begin() as conn:
            conn.execute(delete(email_tokens).where(email_tokens.c.expires_at < now()))
            dead_sessions = conn.execute(delete(sessions).where(sessions.c.expires_at < now())).rowcount
            old_attempts = conn.execute(
                delete(auth_attempts).where(auth_attempts.c.at < attempts_before)).rowcount
        return dead_sessions, old_attempts

    def delete_abandoned_uploads(self, created_before: datetime) -> list[str]:
        """Remove analyses whose video never arrived. Returns their ids (to delete any files)."""
        stale = (analyses.c.status == "awaiting_upload", analyses.c.created_at < created_before)
        with self.engine.begin() as conn:
            ids = list(conn.execute(select(analyses.c.id).where(*stale)).scalars())
            if ids:
                conn.execute(delete(analyses).where(analyses.c.id.in_(ids), *stale))
        return ids

    def expire_inputs(self, uploaded_before: datetime, limit: int = 500) -> list[str]:
        """Analyses whose original upload is due for deletion: uploaded before the cutoff,
        not waiting in the queue or being processed, and not already expired. Returns ids."""
        query = (select(analyses.c.id)
                 .where(analyses.c.created_at < uploaded_before, analyses.c.input_deleted_at.is_(None),
                        analyses.c.status.in_(("succeeded", "failed")))
                 .order_by(analyses.c.created_at).limit(limit))
        with self.engine.connect() as conn:
            return list(conn.execute(query).scalars())

    def mark_input_deleted(self, analysis_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(analyses).where(analyses.c.id == analysis_id).values(input_deleted_at=now()))

    def delete_session(self, token_hash: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(sessions).where(sessions.c.token_hash == token_hash))

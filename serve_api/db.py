"""Persistence (SQLite or Postgres): analyses, which double as the job queue, users, sessions,
emailed tokens and the storage purge queue."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import (
    Connection,
    Engine,
    and_,
    bindparam,
    case,
    create_engine,
    delete,
    event,
    func,
    insert,
    or_,
    select,
    true,
    tuple_,
    type_coerce,
    update,
)
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from .tables import (
    UTCDateTime,
    analyses,
    auth_attempts,
    blocks,
    follows,
    conversation_members,
    conversations,
    email_tokens,
    messages,
    notifications,
    post_comments,
    post_likes,
    posts,
    profiles,
    released_usernames,
    result_reports,
    sessions,
    storage_purges,
    user_reports,
    users,
)

IN_PROGRESS = ("extracting_pose", "analyzing", "rendering")
# How long a username someone gave up stays theirs to take back, so nobody can pose as them.
USERNAME_HELD_FOR = timedelta(days=30)
KEY_POSITIONS = ("front_knee_flexion", "back_knee_flexion", "trunk_tilt", "elbow_angle", "wrist_height")


@dataclass(frozen=True)
class HistoryFilters:
    """History's sidebar: upload time, overall score, and one key position's band."""

    uploaded_from: datetime | None = None
    uploaded_to: datetime | None = None
    min_score: int | None = None
    max_score: int | None = None
    stat: str | None = None       # one of KEY_POSITIONS
    stat_band: str | None = None  # "good" | "borderline" | "off"

    def conditions(self) -> list:
        c = analyses.c
        out = []
        if self.uploaded_from is not None:
            out.append(c.created_at >= self.uploaded_from)
        if self.uploaded_to is not None:
            out.append(c.created_at < self.uploaded_to)
        if self.min_score is not None:
            out.append(c.overall_score >= self.min_score)
        if self.max_score is not None:
            out.append(c.overall_score <= self.max_score)
        if self.stat is not None and self.stat_band is not None:
            out.append(c.key_scores[self.stat]["band"].as_string() == self.stat_band)
        return out
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
        since: datetime, limit: int, camera_view: str | None = None,
    ) -> dict[str, Any] | None:
        """Create an analysis unless the user already created ``limit`` since ``since``."""
        with self._locked_for(user_id) as conn:
            if self._count_created_since(conn, user_id, since) >= limit:
                return None
            return self._insert(conn, user_id, hand, filename, content_type, size_bytes, camera_view)

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
        self, user_id: str, hand: str, filename: str, content_type: str, size_bytes: int,
        camera_view: str | None = None,
    ) -> dict[str, Any]:
        with self.engine.begin() as conn:
            return self._insert(conn, user_id, hand, filename, content_type, size_bytes, camera_view)

    def _insert(
        self, conn: Connection, user_id: str, hand: str, filename: str, content_type: str,
        size_bytes: int, camera_view: str | None = None,
    ) -> dict[str, Any]:
        ts = now()
        row = {
            "id": uuid.uuid4().hex, "user_id": user_id, "hand": hand, "filename": filename,
            "content_type": content_type, "size_bytes": size_bytes, "camera_view": camera_view,
            "status": "awaiting_upload", "error_code": None, "error_message": None,
            "counts": None, "created_at": ts, "updated_at": ts,
            "claim_token": None, "heartbeat_at": None, "attempts": 0, "input_deleted_at": None,
            "overall_score": None, "key_scores": None, "note": None,
        }
        # key_scores is left to its column default, a SQL NULL ("not scored yet"): a Python None in
        # a JSON column would be stored as JSON null, which IS NULL doesn't match.
        conn.execute(insert(analyses).values({k: v for k, v in row.items() if k != "key_scores"}))
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
        self, user_id: str, limit: int, before: tuple[datetime, str] | None = None,
        filters: "HistoryFilters | None" = None,
    ) -> list[dict[str, Any]]:
        """A user's analyses, newest first. ``before`` is a (created_at, id) keyset cursor.
        ``filters`` narrows them by upload time, overall score and one key position's band."""
        query = select(analyses).where(analyses.c.user_id == user_id)
        if filters is not None:
            query = query.where(*filters.conditions())
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

    def create_user(self, email: str, password_hash: str, terms_version: str | None = None,
                    username: str | None = None) -> dict[str, Any] | Literal["username_taken"] | None:
        """Returns None if the email is already registered, "username_taken" if the username is.
        ``email`` must be normalised. ``terms_version`` records the Terms and Privacy Policy
        accepted at signup. With ``username``, the profile is made in the same transaction, so
        the account never exists without it."""
        ts = now()
        row = {"id": uuid.uuid4().hex, "email": email, "password_hash": password_hash,
               "created_at": ts, "email_verified_at": None, "terms_version": terms_version,
               "terms_accepted_at": ts if terms_version else None}
        try:
            with self.engine.begin() as conn:
                conn.execute(insert(users).values(row))
                if username:
                    conn.execute(insert(profiles).values(user_id=row["id"], username=username, updated_at=ts))
        except IntegrityError:
            return None if self.get_user_by_email(email) else "username_taken"
        return row

    def username_unavailable(self, username: str, user_id: str | None = None,
                             held_for: timedelta = USERNAME_HELD_FOR) -> Literal["taken", "held"] | None:
        """Why ``username`` (already valid) can't be ``user_id``'s (None: a new account), or None."""
        owner = self.username_owner(username)
        if owner is not None and owner != user_id:
            return "taken"
        hold = self.username_hold(username)
        # A hold with no owner (the account was deleted) is held for nobody: a new account
        # (user_id None) mustn't count as its owner.
        reclaiming = hold is not None and hold["user_id"] is not None and hold["user_id"] == user_id
        if hold and not reclaiming and hold["released_at"] > now() - held_for:
            return "held"
        return None

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
                           expires_at: datetime, new_email: str | None = None) -> None:
        """Store a new link token. Earlier unused tokens for the same purpose stop working,
        so only the most recent email's link is valid. ``new_email`` is for email changes."""
        with self.engine.begin() as conn:
            conn.execute(delete(email_tokens).where(
                email_tokens.c.user_id == user_id, email_tokens.c.purpose == purpose,
                email_tokens.c.used_at.is_(None)))
            conn.execute(insert(email_tokens).values(
                id=uuid.uuid4().hex, user_id=user_id, purpose=purpose, token_hash=token_hash,
                created_at=now(), expires_at=expires_at, used_at=None, new_email=new_email))

    def use_email_token(self, token_hash: str, purpose: str) -> str | None:
        """Spend a token: returns its user id, or None if it's unknown, used or expired."""
        spent = self._spend_email_token(token_hash, purpose)
        return spent[0] if spent else None

    def _spend_email_token(self, token_hash: str, purpose: str) -> tuple[str, str | None] | None:
        """(user id, new email) for a live token, marking it used. One UPDATE makes it
        single-use even when two requests race."""
        with self.engine.begin() as conn:
            row = conn.execute(
                update(email_tokens)
                .where(email_tokens.c.token_hash == token_hash, email_tokens.c.purpose == purpose,
                       email_tokens.c.used_at.is_(None), email_tokens.c.expires_at > now())
                .values(used_at=now())
                .returning(email_tokens.c.user_id, email_tokens.c.new_email)
            ).first()
        return (row[0], row[1]) if row else None

    def change_email(self, token_hash: str) -> tuple[str, str, str] | Literal["invalid", "taken"]:
        """Spend an email-change token and switch the account to its new address.

        Returns (user id, old email, new email); "invalid" for an unknown, used or expired
        link; "taken" if another account registered the address after the link was sent.
        Opening the link proves control of the new inbox, so the address counts as verified.
        """
        spent = self._spend_email_token(token_hash, "email_change")
        if spent is None or spent[1] is None:
            return "invalid"
        user_id, new_email = spent
        old = self.get_user(user_id)
        if old is None:
            return "invalid"
        try:
            with self.engine.begin() as conn:
                conn.execute(update(users).where(users.c.id == user_id)
                             .values(email=new_email, email_verified_at=now()))
        except IntegrityError:
            return "taken"
        return user_id, old["email"], new_email

    # --- deletion ----------------------------------------------------------------

    @staticmethod
    def _queue_purges(conn: Connection, prefixes: list[str]) -> list[int]:
        ts = now()
        return [conn.execute(insert(storage_purges).values(prefix=p, created_at=ts)).inserted_primary_key[0]
                for p in prefixes]

    def queue_purges(self, prefixes: list[str]) -> list[int]:
        """Queue storage prefixes for deletion (see storage_purges); run them with purge.run_purges."""
        with self.engine.begin() as conn:
            return self._queue_purges(conn, prefixes)

    def delete_analysis(self, analysis_id: str, user_id: str, prefixes: list[str]) -> list[int] | None:
        """Delete one of ``user_id``'s analyses and queue its storage ``prefixes`` for removal,
        in one transaction. Returns the purge ids, or None if there was no such analysis.
        Messages it was sent in stay, saying the serve isn't available any more."""
        with self.engine.begin() as conn:
            conn.execute(update(messages).where(messages.c.analysis_id == analysis_id,
                                                messages.c.sender_id == user_id).values(analysis_id=None))
            conn.execute(delete(result_reports).where(
                result_reports.c.analysis_id == analysis_id, result_reports.c.user_id == user_id))
            gone = conn.execute(delete(analyses).where(
                analyses.c.id == analysis_id, analyses.c.user_id == user_id)).rowcount
            return self._queue_purges(conn, prefixes) if gone else None

    def delete_user(self, user_id: str, prefixes_for: Any, account_prefixes: list[str] | None = None) -> list[int]:
        """Delete an account with its sessions, tokens, profile and analyses, queueing every
        analysis's storage (``prefixes_for(analysis_id)``) and ``account_prefixes`` (its profile
        picture) for removal. Returns the purge ids."""
        with self.engine.begin() as conn:
            ids = list(conn.execute(select(analyses.c.id).where(analyses.c.user_id == user_id)).scalars())
            post_ids = list(conn.execute(select(posts.c.id).where(posts.c.user_id == user_id)).scalars())
            if post_ids:
                conn.execute(delete(post_likes).where(post_likes.c.post_id.in_(post_ids)))
                conn.execute(delete(post_comments).where(post_comments.c.post_id.in_(post_ids)))
                conn.execute(delete(posts).where(posts.c.id.in_(post_ids)))
            conn.execute(delete(post_likes).where(post_likes.c.user_id == user_id))
            conn.execute(delete(post_comments).where(post_comments.c.user_id == user_id))
            account_prefixes = (account_prefixes or []) + [f"posts/{pid}" for pid in post_ids]
            # Their username is held for a while, so nobody can take it to pose as them.
            if name := conn.execute(select(profiles.c.username).where(profiles.c.user_id == user_id)).scalar_one_or_none():
                self._hold(conn, name, None)
            conn.execute(delete(notifications).where(or_(notifications.c.user_id == user_id,
                                                         notifications.c.actor_id == user_id)))
            purge_ids = self._queue_purges(conn, [p for i in ids for p in prefixes_for(i)] + (account_prefixes or []))
            # Explicit deletes rather than relying on ON DELETE CASCADE alone.
            for table in (result_reports, analyses, sessions, email_tokens, profiles):
                conn.execute(delete(table).where(table.c.user_id == user_id))
            conn.execute(delete(follows).where(or_(follows.c.follower_id == user_id, follows.c.followee_id == user_id)))
            conn.execute(delete(blocks).where(or_(blocks.c.blocker_id == user_id, blocks.c.blocked_id == user_id)))
            # Messages they sent go; the other person keeps their side of the conversation.
            conn.execute(delete(messages).where(messages.c.sender_id == user_id))
            conn.execute(delete(conversation_members).where(conversation_members.c.user_id == user_id))
            conn.execute(delete(conversations).where(~conversations.c.id.in_(
                select(conversation_members.c.conversation_id))))
            # Reports stay for review, without the deleted account's id.
            conn.execute(update(user_reports).where(user_reports.c.reporter_id == user_id).values(reporter_id=None))
            conn.execute(update(user_reports).where(user_reports.c.reported_id == user_id).values(reported_id=None))
            conn.execute(delete(users).where(users.c.id == user_id))
        return purge_ids

    # --- reports that a result looks wrong -------------------------------------------

    def save_report(self, analysis: dict[str, Any], reason: str, note: str | None) -> dict[str, Any]:
        """Record (or replace) the owner's report on ``analysis``, with its current status."""
        row = {"analysis_id": analysis["id"], "user_id": analysis["user_id"], "reason": reason,
               "note": note, "status": analysis["status"], "error_code": analysis["error_code"],
               "created_at": now()}
        with self.engine.begin() as conn:
            conn.execute(delete(result_reports).where(result_reports.c.analysis_id == analysis["id"]))
            conn.execute(insert(result_reports).values(row))
        return row

    def get_report(self, analysis_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(result_reports).where(
                result_reports.c.analysis_id == analysis_id)).mappings().first()
        return dict(row) if row else None

    def reports(self, since: datetime | None = None) -> list[dict[str, Any]]:
        """Every report, oldest first, with its analysis's hand, upload time and whether the
        original video has been deleted."""
        query = (select(result_reports, analyses.c.hand, analyses.c.camera_view,
                        analyses.c.created_at.label("uploaded_at"), analyses.c.input_deleted_at)
                 .join(analyses, analyses.c.id == result_reports.c.analysis_id)
                 .order_by(result_reports.c.created_at))
        if since is not None:
            query = query.where(result_reports.c.created_at >= since)
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(query).mappings()]

    def user_reports(self, user_id: str) -> dict[str, dict[str, Any]]:
        """A user's reports, by analysis id."""
        with self.engine.connect() as conn:
            rows = conn.execute(select(result_reports).where(
                result_reports.c.user_id == user_id)).mappings()
            return {r["analysis_id"]: dict(r) for r in rows}

    def all_analyses(self, user_id: str) -> list[dict[str, Any]]:
        """Every analysis a user has, oldest first (for their data export)."""
        query = (select(analyses).where(analyses.c.user_id == user_id)
                 .order_by(analyses.c.created_at, analyses.c.id))
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(query).mappings()]

    def pending_purges(self, ids: list[int] | None = None) -> list[tuple[int, str]]:
        query = select(storage_purges.c.id, storage_purges.c.prefix).order_by(storage_purges.c.id)
        if ids is not None:
            query = query.where(storage_purges.c.id.in_(ids))
        with self.engine.connect() as conn:
            return [(r[0], r[1]) for r in conn.execute(query)]

    def finish_purge(self, purge_id: int) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(storage_purges).where(storage_purges.c.id == purge_id))

    def change_password(self, user_id: str, password_hash: str, keep_session: str) -> None:
        """A new password from the signed-in Settings page: every other session is signed out
        (the one with token hash ``keep_session`` stays), and outstanding reset links stop working."""
        with self.engine.begin() as conn:
            conn.execute(update(users).where(users.c.id == user_id).values(password_hash=password_hash))
            conn.execute(delete(sessions).where(sessions.c.user_id == user_id, sessions.c.token_hash != keep_session))
            conn.execute(delete(email_tokens).where(email_tokens.c.user_id == user_id,
                                                    email_tokens.c.purpose == "reset"))

    # --- profiles --------------------------------------------------------------

    def get_profile(self, user_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(profiles).where(profiles.c.user_id == user_id)).mappings().first()
        return dict(row) if row else None

    def username_owner(self, username: str) -> str | None:
        with self.engine.connect() as conn:
            return conn.execute(select(profiles.c.user_id).where(profiles.c.username == username)).scalar_one_or_none()

    def save_profile(self, user_id: str, held_for: timedelta | None = None,
                     **fields: Any) -> dict[str, Any] | Literal["username_taken", "username_held"]:
        """Set some of a profile's fields, creating the row the first time. "username_taken" if
        someone else has the username (checked by the unique index, so two people can't race to
        it); "username_held" if someone else gave it up less than ``held_for`` ago. A username
        given up here is held in turn, for its owner to take back."""
        fields["updated_at"] = now()
        new_name = fields.get("username")
        if new_name and held_for:
            if self.username_unavailable(new_name, user_id, held_for) == "held":
                return "username_held"
        try:
            with self.engine.begin() as conn:
                old_name = conn.execute(select(profiles.c.username).where(profiles.c.user_id == user_id)).scalar_one_or_none()
                done = conn.execute(update(profiles).where(profiles.c.user_id == user_id).values(**fields)).rowcount
                if not done:
                    conn.execute(insert(profiles).values(user_id=user_id, **fields))
                if new_name and old_name and new_name != old_name:
                    self._hold(conn, old_name, user_id)
                if new_name:  # taking a name back (or a fresh one) ends any hold on it
                    conn.execute(delete(released_usernames).where(released_usernames.c.username == new_name,
                                                                  released_usernames.c.user_id == user_id))
        except IntegrityError:
            if "username" in fields and self.username_owner(fields["username"]) not in (None, user_id):
                return "username_taken"
            # Two first saves at once: the other one made the row, so this one is an update.
            with self.engine.begin() as conn:
                conn.execute(update(profiles).where(profiles.c.user_id == user_id).values(**fields))
        return self.get_profile(user_id) or {}

    def profile_stats(self, user_id: str, recent: int = 10) -> dict[str, Any]:
        """Finished serves, and the average of the latest ``recent`` scored ones, for the profile."""
        mine = (analyses.c.user_id == user_id, analyses.c.status == "succeeded")
        with self.engine.connect() as conn:
            serves, best = conn.execute(select(func.count(), func.max(analyses.c.overall_score)).where(*mine)).one()
            latest = list(conn.execute(
                select(analyses.c.overall_score).where(*mine, analyses.c.overall_score.is_not(None))
                .order_by(analyses.c.created_at.desc(), analyses.c.id.desc()).limit(recent)).scalars())
        return {"serves": serves, "best_score": best, "averaged_over": len(latest),
                "average_score": int(sum(latest) / len(latest) + 0.5) if latest else None}  # half up, like scores

    def serve_summary(self, user_id: str, recent: int = 10, trend: int = 20) -> dict[str, Any]:
        """What a friend may be shown of ``user_id``'s serves: the profile's stats, plus the latest
        ``trend`` scores (oldest first), the change between the latest five and the five before,
        and each key position's average over the latest ``recent`` serves it was measured in."""
        mine = (analyses.c.user_id == user_id, analyses.c.status == "succeeded")
        with self.engine.connect() as conn:
            serves, best = conn.execute(select(func.count(), func.max(analyses.c.overall_score)).where(*mine)).one()
            rows = conn.execute(
                select(analyses.c.overall_score, analyses.c.key_scores, analyses.c.created_at)
                .where(*mine, analyses.c.overall_score.is_not(None))
                .order_by(analyses.c.created_at.desc(), analyses.c.id.desc()).limit(max(recent, trend))).all()
        mean = lambda xs: int(sum(xs) / len(xs) + 0.5) if xs else None  # noqa: E731  (half up, like scores)
        latest = rows[:recent]
        scores = [r.overall_score for r in rows]
        positions = {}
        for metric in KEY_POSITIONS:
            measured = [r.key_scores[metric]["score"] for r in latest
                        if isinstance(r.key_scores, dict) and isinstance(r.key_scores.get(metric), dict)]
            positions[metric] = {"score": mean(measured), "measured": len(measured)} if measured else None
        return {
            "serves": serves, "best_score": best, "averaged_over": len(latest),
            "average_score": mean([r.overall_score for r in latest]),
            "trend": [{"at": r.created_at, "score": r.overall_score} for r in reversed(rows[:trend])],
            "change": mean(scores[:5]) - mean(scores[5:10]) if len(scores) >= 10 else None,
            "positions": positions,
        }

    def leaderboard_numbers(self, user_ids: list[str], since: datetime, recent: int = 10) -> dict[str, dict[str, Any]]:
        """For each person: how many scored serves they have since ``since``, and the average of
        the latest ``recent`` of them."""
        out: dict[str, dict[str, Any]] = {uid: {"scored": 0, "average": None} for uid in user_ids}
        if not user_ids:
            return out
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(analyses.c.user_id, analyses.c.overall_score)
                .where(analyses.c.user_id.in_(user_ids), analyses.c.status == "succeeded",
                       analyses.c.overall_score.is_not(None), analyses.c.created_at >= since)
                .order_by(analyses.c.user_id, analyses.c.created_at.desc(), analyses.c.id.desc())).all()
        latest: dict[str, list[int]] = {}
        for r in rows:
            out[r.user_id]["scored"] += 1
            if len(latest.setdefault(r.user_id, [])) < recent:
                latest[r.user_id].append(r.overall_score)
        for uid, xs in latest.items():
            out[uid]["average"] = int(sum(xs) / len(xs) + 0.5)
        return out

    # --- friends ---------------------------------------------------------------

    @staticmethod
    def pair_of(a: str, b: str) -> str:
        return ":".join(sorted((a, b)))

    def person_by_username(self, username: str) -> dict[str, Any] | None:
        """A profile with a username (``user_id`` included), or None."""
        with self.engine.connect() as conn:
            row = conn.execute(select(profiles).where(profiles.c.username == username)).mappings().first()
        return dict(row) if row else None

    def profiles_of(self, user_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not user_ids:
            return {}
        with self.engine.connect() as conn:
            rows = conn.execute(select(profiles).where(profiles.c.user_id.in_(user_ids))).mappings().all()
        return {r["user_id"]: dict(r) for r in rows}

    def hidden_between(self, a: str, b: str) -> bool:
        """Whether the two are hidden from each other: either has blocked the other, or either
        account is suspended. Everything that respects blocks (finding someone, conversations,
        shared serves) respects suspensions through this."""
        with self.engine.connect() as conn:
            blocked = conn.execute(select(func.count()).select_from(blocks).where(or_(
                and_(blocks.c.blocker_id == a, blocks.c.blocked_id == b),
                and_(blocks.c.blocker_id == b, blocks.c.blocked_id == a)))).scalar_one() > 0
            suspended = conn.execute(select(func.count()).select_from(users).where(
                users.c.id.in_((a, b)), users.c.suspended_at.is_not(None))).scalar_one() > 0
        return blocked or suspended

    def suspended_ids(self) -> Any:
        """A subquery of suspended accounts' ids, for leaving them out of lists."""
        return select(users.c.id).where(users.c.suspended_at.is_not(None))

    def suspend(self, user_id: str, reason: str) -> None:
        """Suspend an account: it can't sign in (every session ends) and is hidden from everyone."""
        with self.engine.begin() as conn:
            conn.execute(update(users).where(users.c.id == user_id).values(suspended_at=now(), suspended_reason=reason))
            conn.execute(delete(sessions).where(sessions.c.user_id == user_id))

    def unsuspend(self, user_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(users).where(users.c.id == user_id).values(suspended_at=None, suspended_reason=None))

    # --- posts -----------------------------------------------------------------

    def create_post(self, row: dict[str, Any]) -> dict[str, Any]:
        with self.engine.begin() as conn:
            conn.execute(insert(posts).values(**row))
        return row

    def get_post(self, post_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(posts).where(posts.c.id == post_id)).mappings().first()
        return dict(row) if row else None

    def update_post(self, post_id: str, user_id: str, **fields: Any) -> bool:
        """Change one of ``user_id``'s posts; False if it isn't theirs (or doesn't exist)."""
        with self.engine.begin() as conn:
            return conn.execute(update(posts).where(posts.c.id == post_id, posts.c.user_id == user_id)
                                .values(updated_at=now(), **fields)).rowcount > 0

    def delete_post(self, post_id: str, user_id: str, prefixes: list[str]) -> list[int] | None:
        """Delete one of ``user_id``'s posts with its likes and comments, and queue its files for
        removal, in one transaction. None if there was no such post of theirs."""
        with self.engine.begin() as conn:
            mine = conn.execute(select(posts.c.id).where(posts.c.id == post_id, posts.c.user_id == user_id)).first()
            if mine is None:
                return None
            conn.execute(delete(post_likes).where(post_likes.c.post_id == post_id))
            conn.execute(delete(post_comments).where(post_comments.c.post_id == post_id))
            conn.execute(delete(posts).where(posts.c.id == post_id))
            return self._queue_purges(conn, prefixes)

    def posts_by(self, user_id: str, visibilities: tuple[str, ...], limit: int,
                 before: tuple[datetime, str] | None = None) -> list[dict[str, Any]]:
        """``user_id``'s posts with one of ``visibilities``, newest first."""
        query = select(posts).where(posts.c.user_id == user_id, posts.c.visibility.in_(visibilities))
        if before:
            query = query.where(tuple_(posts.c.created_at, posts.c.id) < tuple_(
                bindparam("p_at", before[0], UTCDateTime), bindparam("p_id", before[1])))
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(query.order_by(posts.c.created_at.desc(), posts.c.id.desc()).limit(limit)).mappings()]

    def feed_page(self, viewer_id: str, tab: str, limit: int,
                  before: tuple[datetime, str] | None = None) -> list[dict[str, Any]]:
        """The feed, newest first. "public": everyone's public posts. "friends": public and
        friends posts from ``viewer_id``'s friends (people they follow who follow them back).
        Both leave out anyone hidden from the viewer (a block either way, or a suspension)."""
        query = select(posts).where(posts.c.user_id.not_in(self.hidden_from(viewer_id)))
        if tab == "public":
            query = query.where(posts.c.visibility == "public")
        elif tab == "friends":
            query = query.where(posts.c.user_id.in_(self.friends_of(viewer_id)))
        else:
            raise ValueError(tab)
        if before:
            query = query.where(tuple_(posts.c.created_at, posts.c.id) < tuple_(
                bindparam("f_at", before[0], UTCDateTime), bindparam("f_id", before[1])))
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(
                query.order_by(posts.c.created_at.desc(), posts.c.id.desc()).limit(limit)).mappings()]

    def like(self, post_id: str, user_id: str) -> bool:
        """Like a post; True if it's new. A second like is a no-op (the primary key)."""
        try:
            with self.engine.begin() as conn:
                exists = conn.execute(select(func.count()).select_from(post_likes).where(
                    post_likes.c.post_id == post_id, post_likes.c.user_id == user_id)).scalar_one()
                if exists:
                    return False
                conn.execute(insert(post_likes).values(post_id=post_id, user_id=user_id, created_at=now()))
        except IntegrityError:
            return False
        return True

    def unlike(self, post_id: str, user_id: str) -> bool:
        with self.engine.begin() as conn:
            return conn.execute(delete(post_likes).where(
                post_likes.c.post_id == post_id, post_likes.c.user_id == user_id)).rowcount > 0

    def post_counts(self, post_ids: list[str], viewer_id: str) -> dict[str, dict[str, Any]]:
        """For each post: likes and comments (leaving out suspended accounts), and whether
        ``viewer_id`` liked it."""
        out = {pid: {"likes": 0, "comments": 0, "liked": False} for pid in post_ids}
        if not post_ids:
            return out
        gone = self.suspended_ids()
        with self.engine.connect() as conn:
            for pid, n in conn.execute(select(post_likes.c.post_id, func.count()).where(
                    post_likes.c.post_id.in_(post_ids), post_likes.c.user_id.not_in(gone)).group_by(post_likes.c.post_id)):
                out[pid]["likes"] = n
            for pid, n in conn.execute(select(post_comments.c.post_id, func.count()).where(
                    post_comments.c.post_id.in_(post_ids), post_comments.c.user_id.not_in(gone)).group_by(post_comments.c.post_id)):
                out[pid]["comments"] = n
            for pid in conn.execute(select(post_likes.c.post_id).where(
                    post_likes.c.post_id.in_(post_ids), post_likes.c.user_id == viewer_id)).scalars():
                out[pid]["liked"] = True
        return out

    def add_comment(self, post_id: str, user_id: str, body: str) -> dict[str, Any]:
        row = {"id": uuid.uuid4().hex, "post_id": post_id, "user_id": user_id, "body": body, "created_at": now()}
        with self.engine.begin() as conn:
            conn.execute(insert(post_comments).values(**row))
        return row

    def get_comment(self, comment_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(post_comments).where(post_comments.c.id == comment_id)).mappings().first()
        return dict(row) if row else None

    def delete_comment(self, comment_id: str) -> bool:
        with self.engine.begin() as conn:
            return conn.execute(delete(post_comments).where(post_comments.c.id == comment_id)).rowcount > 0

    def comments_page(self, post_id: str, viewer_id: str, limit: int,
                      after: tuple[datetime, str] | None = None) -> list[dict[str, Any]]:
        """Oldest first, leaving out suspended accounts and anyone hidden from ``viewer_id``."""
        hidden = select(blocks.c.blocked_id).where(blocks.c.blocker_id == viewer_id).union(
            select(blocks.c.blocker_id).where(blocks.c.blocked_id == viewer_id), self.suspended_ids())
        query = select(post_comments).where(post_comments.c.post_id == post_id, post_comments.c.user_id.not_in(hidden))
        if after:
            query = query.where(tuple_(post_comments.c.created_at, post_comments.c.id) > tuple_(
                bindparam("c_at", after[0], UTCDateTime), bindparam("c_id", after[1])))
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(
                query.order_by(post_comments.c.created_at, post_comments.c.id).limit(limit)).mappings()]

    def count_since(self, table_name: str, user_id: str, since: datetime) -> int:
        """How many posts or comments ``user_id`` made since ``since`` (for rate limits)."""
        table = {"posts": posts, "comments": post_comments}[table_name]
        with self.engine.connect() as conn:
            return conn.execute(select(func.count()).select_from(table).where(
                table.c.user_id == user_id, table.c.created_at >= since)).scalar_one()

    def likes_by(self, user_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(select(post_likes).where(post_likes.c.user_id == user_id)).mappings()]

    def comments_by(self, user_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(select(post_comments).where(post_comments.c.user_id == user_id)
                                                  .order_by(post_comments.c.created_at)).mappings()]

    # --- notifications ---------------------------------------------------------

    def notify(self, user_id: str, kind: str, actor_id: str, conversation_id: str | None = None) -> None:
        with self.engine.begin() as conn:
            conn.execute(insert(notifications).values(
                id=uuid.uuid4().hex, user_id=user_id, kind=kind, actor_id=actor_id,
                conversation_id=conversation_id, created_at=now(), read_at=None))

    def notifications_for(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Newest first, leaving out anyone hidden from ``user_id`` (blocked or suspended)."""
        hidden = select(blocks.c.blocked_id).where(blocks.c.blocker_id == user_id).union(
            select(blocks.c.blocker_id).where(blocks.c.blocked_id == user_id), self.suspended_ids())
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(
                select(notifications).where(notifications.c.user_id == user_id, notifications.c.actor_id.not_in(hidden))
                .order_by(notifications.c.created_at.desc()).limit(limit)).mappings()]

    def mark_notifications_read(self, user_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(notifications).where(notifications.c.user_id == user_id,
                                                     notifications.c.read_at.is_(None)).values(read_at=now()))

    def forget_notifications_between(self, a: str, b: str, kinds: tuple[str, ...] | None = None) -> None:
        """Drop notifications either person got from the other (of ``kinds``, or all)."""
        cond = or_(and_(notifications.c.user_id == a, notifications.c.actor_id == b),
                   and_(notifications.c.user_id == b, notifications.c.actor_id == a))
        with self.engine.begin() as conn:
            conn.execute(delete(notifications).where(cond, notifications.c.kind.in_(kinds) if kinds else true()))

    def delete_old_notifications(self, before: datetime) -> int:
        with self.engine.begin() as conn:
            return conn.execute(delete(notifications).where(notifications.c.created_at < before)).rowcount

    # --- usernames people gave up ----------------------------------------------

    def username_hold(self, username: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(released_usernames).where(released_usernames.c.username == username)).mappings().first()
        return dict(row) if row else None

    def delete_old_username_holds(self, before: datetime) -> int:
        with self.engine.begin() as conn:
            return conn.execute(delete(released_usernames).where(released_usernames.c.released_at < before)).rowcount

    @staticmethod
    def _hold(conn: Connection, username: str, user_id: str | None) -> None:
        conn.execute(delete(released_usernames).where(released_usernames.c.username == username))
        conn.execute(insert(released_usernames).values(username=username, user_id=user_id, released_at=now()))

    def follow(self, follower_id: str, followee_id: str) -> bool:
        """Follow someone; True if it's new. Following twice is a no-op (and two taps at once are
        settled by the primary key), and nobody can follow themselves (the check constraint)."""
        if follower_id == followee_id:
            raise ValueError("can't follow yourself")
        try:
            with self.engine.begin() as conn:
                exists = conn.execute(select(func.count()).select_from(follows).where(
                    follows.c.follower_id == follower_id, follows.c.followee_id == followee_id)).scalar_one()
                if exists:
                    return False
                conn.execute(insert(follows).values(follower_id=follower_id, followee_id=followee_id, created_at=now()))
        except IntegrityError:  # the other tap won
            return False
        return True

    def unfollow(self, follower_id: str, followee_id: str) -> bool:
        """Stop following (also how a follower is removed: unfollow(them, you)). True if it did."""
        with self.engine.begin() as conn:
            return conn.execute(delete(follows).where(
                follows.c.follower_id == follower_id, follows.c.followee_id == followee_id)).rowcount > 0

    def follow_row(self, follower_id: str, followee_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(follows).where(
                follows.c.follower_id == follower_id, follows.c.followee_id == followee_id)).mappings().first()
        return dict(row) if row else None

    def are_friends(self, a: str, b: str | None) -> bool:
        """Friends: each follows the other."""
        if not b or a == b:
            return False
        with self.engine.connect() as conn:
            return conn.execute(select(func.count()).select_from(follows).where(or_(
                and_(follows.c.follower_id == a, follows.c.followee_id == b),
                and_(follows.c.follower_id == b, follows.c.followee_id == a)))).scalar_one() == 2

    def _list_query(self, user_id: str, kind: str, viewer_id: str | None = None):
        """``user_id``'s followers, following or friends as (user_id, since), leaving out
        suspended accounts and, when someone else is looking, anyone hidden from them. A
        friend's ``since`` is when the second of the two follows happened."""
        gone = self.suspended_ids()
        if kind == "followers":
            query = select(follows.c.follower_id.label("user_id"), follows.c.created_at.label("since")).where(
                follows.c.followee_id == user_id, follows.c.follower_id.not_in(gone))
        elif kind == "following":
            query = select(follows.c.followee_id.label("user_id"), follows.c.created_at.label("since")).where(
                follows.c.follower_id == user_id, follows.c.followee_id.not_in(gone))
        elif kind == "friends":
            out, back = follows.alias("out"), follows.alias("back")
            later = type_coerce(case((out.c.created_at > back.c.created_at, out.c.created_at), else_=back.c.created_at),
                                UTCDateTime)
            query = (select(out.c.followee_id.label("user_id"), later.label("since"))
                     .join(back, and_(back.c.follower_id == out.c.followee_id, back.c.followee_id == user_id))
                     .where(out.c.follower_id == user_id, out.c.followee_id.not_in(gone)))
        else:
            raise ValueError(kind)
        if viewer_id and viewer_id != user_id:
            hidden = select(blocks.c.blocked_id).where(blocks.c.blocker_id == viewer_id).union(
                select(blocks.c.blocker_id).where(blocks.c.blocked_id == viewer_id))
            query = query.where(query.selected_columns.user_id.not_in(hidden))
        return query

    def follow_page(self, user_id: str, kind: str, limit: int, before: tuple[datetime, str] | None = None,
                    viewer_id: str | None = None) -> list[dict[str, Any]]:
        """A page of one of ``user_id``'s lists, newest first; ``before`` is the last row's
        (since, user_id) from the page before."""
        sub = self._list_query(user_id, kind, viewer_id).subquery()
        query = select(sub)
        if before:
            query = query.where(tuple_(sub.c.since, sub.c.user_id) < tuple_(bindparam("b_at", before[0], UTCDateTime),
                                                                            bindparam("b_id", before[1])))
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(query.order_by(sub.c.since.desc(), sub.c.user_id.desc()).limit(limit)).mappings()]

    def follow_lists(self, user_id: str) -> dict[str, list[dict[str, Any]]]:
        """All three lists in full, newest first (for the data download)."""
        return {kind: self.follow_page(user_id, kind, limit=1_000_000) for kind in ("followers", "following", "friends")}

    def follow_counts(self, user_id: str) -> dict[str, int]:
        with self.engine.connect() as conn:
            return {kind: conn.execute(select(func.count()).select_from(self._list_query(user_id, kind).subquery())).scalar_one()
                    for kind in ("followers", "following", "friends")}

    def follows_among(self, viewer_id: str, user_ids: list[str]) -> tuple[set[str], set[str]]:
        """Of ``user_ids``, who ``viewer_id`` follows, and who follows ``viewer_id``."""
        if not user_ids:
            return set(), set()
        with self.engine.connect() as conn:
            you = set(conn.execute(select(follows.c.followee_id).where(
                follows.c.follower_id == viewer_id, follows.c.followee_id.in_(user_ids))).scalars())
            them = set(conn.execute(select(follows.c.follower_id).where(
                follows.c.followee_id == viewer_id, follows.c.follower_id.in_(user_ids))).scalars())
        return you, them

    def friend_ids(self, user_id: str) -> list[str]:
        return [f["user_id"] for f in self.follow_lists(user_id)["friends"]]

    def friends_since(self, a: str, b: str) -> datetime | None:
        one, other = self.follow_row(a, b), self.follow_row(b, a)
        return max(one["created_at"], other["created_at"]) if one and other else None

    def block(self, blocker_id: str, blocked_id: str) -> None:
        """Block someone: neither follows the other any more (so any friendship ends)."""
        self.forget_notifications_between(blocker_id, blocked_id)
        with self.engine.begin() as conn:
            conn.execute(delete(follows).where(or_(
                and_(follows.c.follower_id == blocker_id, follows.c.followee_id == blocked_id),
                and_(follows.c.follower_id == blocked_id, follows.c.followee_id == blocker_id))))
            exists = conn.execute(select(func.count()).select_from(blocks).where(
                blocks.c.blocker_id == blocker_id, blocks.c.blocked_id == blocked_id)).scalar_one()
            if not exists:
                conn.execute(insert(blocks).values(blocker_id=blocker_id, blocked_id=blocked_id, created_at=now()))

    def unblock(self, blocker_id: str, blocked_id: str) -> bool:
        with self.engine.begin() as conn:
            return conn.execute(delete(blocks).where(
                blocks.c.blocker_id == blocker_id, blocks.c.blocked_id == blocked_id)).rowcount > 0

    def blocked_by(self, blocker_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(select(blocks).where(blocks.c.blocker_id == blocker_id)
                                                  .order_by(blocks.c.created_at.desc())).mappings()]

    # --- messages --------------------------------------------------------------

    def conversation_with(self, a: str, b: str, create: bool = False) -> dict[str, Any] | None:
        """The conversation between two people, made the first time when ``create``."""
        pair = self.pair_of(a, b)
        with self.engine.connect() as conn:
            row = conn.execute(select(conversations).where(conversations.c.pair == pair)).mappings().first()
        if row or not create:
            return dict(row) if row else None
        ts = now()
        new = {"id": uuid.uuid4().hex, "pair": pair, "created_at": ts, "last_message_at": ts}
        try:
            with self.engine.begin() as conn:
                conn.execute(insert(conversations).values(**new))
                for uid in (a, b):
                    conn.execute(insert(conversation_members).values(conversation_id=new["id"], user_id=uid))
        except IntegrityError:  # both opened it at once: use the one that won
            return self.conversation_with(a, b)
        return new

    def membership(self, conversation_id: str, user_id: str) -> dict[str, Any] | None:
        """``user_id``'s side of a conversation, with ``other_id`` (None if they deleted their
        account) and the other person's ``other_read_at``; None if ``user_id`` isn't in it."""
        with self.engine.connect() as conn:
            members = conn.execute(select(conversation_members).where(
                conversation_members.c.conversation_id == conversation_id)).mappings().all()
        mine = next((m for m in members if m["user_id"] == user_id), None)
        if mine is None:
            return None
        other = next((m for m in members if m["user_id"] != user_id), None)
        return {"conversation_id": conversation_id, "last_read_at": mine["last_read_at"],
                "other_id": other["user_id"] if other else None,
                "other_read_at": other["last_read_at"] if other else None}

    def conversations_of(self, user_id: str) -> list[dict[str, Any]]:
        """``user_id``'s conversations that have messages, newest first, each with the other
        person's id, the last message and how many are unread."""
        me = conversation_members.alias("me")
        them = conversation_members.alias("them")
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(conversations.c.id, conversations.c.last_message_at, me.c.last_read_at,
                       them.c.user_id.label("other_id"))
                .join(me, and_(me.c.conversation_id == conversations.c.id, me.c.user_id == user_id))
                .outerjoin(them, and_(them.c.conversation_id == conversations.c.id, them.c.user_id != user_id))
                .order_by(conversations.c.last_message_at.desc())).mappings().all()
            out = []
            for r in rows:
                last = conn.execute(select(messages).where(messages.c.conversation_id == r["id"])
                                    .order_by(messages.c.created_at.desc(), messages.c.id.desc()).limit(1)).mappings().first()
                if last is None:
                    continue
                unread = conn.execute(select(func.count()).select_from(messages).where(
                    messages.c.conversation_id == r["id"], messages.c.sender_id != user_id,
                    messages.c.deleted_at.is_(None),
                    messages.c.created_at > r["last_read_at"] if r["last_read_at"] else true())).scalar_one()
                out.append({**dict(r), "last": dict(last), "unread": unread})
        return out

    def messages_page(self, conversation_id: str, limit: int, before: tuple[datetime, str] | None = None) -> list[dict[str, Any]]:
        """Newest first, older than ``before`` (created_at, id) when given."""
        query = select(messages).where(messages.c.conversation_id == conversation_id)
        if before:
            query = query.where(tuple_(messages.c.created_at, messages.c.id) < tuple_(*before))
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(
                query.order_by(messages.c.created_at.desc(), messages.c.id.desc()).limit(limit)).mappings()]

    def get_message(self, message_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(messages).where(messages.c.id == message_id)).mappings().first()
        return dict(row) if row else None

    def add_message(self, conversation_id: str, sender_id: str, body: str | None,
                    analysis_id: str | None = None) -> dict[str, Any]:
        ts = now()
        row = {"id": uuid.uuid4().hex, "conversation_id": conversation_id, "sender_id": sender_id,
               "body": body, "analysis_id": analysis_id, "created_at": ts, "deleted_at": None}
        with self.engine.begin() as conn:
            conn.execute(insert(messages).values(**row))
            conn.execute(update(conversations).where(conversations.c.id == conversation_id).values(last_message_at=ts))
            # Sending counts as having read everything before it.
            conn.execute(update(conversation_members).where(
                conversation_members.c.conversation_id == conversation_id,
                conversation_members.c.user_id == sender_id).values(last_read_at=ts))
        return row

    def mark_read(self, conversation_id: str, user_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(conversation_members).where(
                conversation_members.c.conversation_id == conversation_id,
                conversation_members.c.user_id == user_id).values(last_read_at=now()))

    def delete_message(self, message_id: str, sender_id: str) -> bool:
        """Delete one of ``sender_id``'s messages for everyone: its text goes, a marker stays."""
        with self.engine.begin() as conn:
            # The serve goes with it: deleting the message is how you stop sharing it.
            return conn.execute(update(messages).where(
                messages.c.id == message_id, messages.c.sender_id == sender_id, messages.c.deleted_at.is_(None))
                .values(body=None, analysis_id=None, deleted_at=now())).rowcount > 0

    def shared_by(self, analysis_id: str, viewer_id: str) -> str | None:
        """Who shared ``analysis_id`` with ``viewer_id``, if anyone still is: its owner sent it in
        a message (not deleted) in a conversation ``viewer_id`` is in, they're friends now, and
        there's no block either way. Otherwise None."""
        with self.engine.connect() as conn:
            owner = conn.execute(
                select(analyses.c.user_id)
                .join(messages, and_(messages.c.analysis_id == analyses.c.id, messages.c.sender_id == analyses.c.user_id))
                .join(conversation_members, and_(conversation_members.c.conversation_id == messages.c.conversation_id,
                                                 conversation_members.c.user_id == viewer_id))
                .where(analyses.c.id == analysis_id, messages.c.deleted_at.is_(None), analyses.c.user_id != viewer_id)
                .limit(1)).scalar_one_or_none()
        if owner is None or self.hidden_between(owner, viewer_id):
            return None
        return owner if self.are_friends(owner, viewer_id) else None

    def hidden_from(self, viewer_id: str) -> Any:
        """A subquery of the ids hidden from ``viewer_id``: a block either way, or suspended."""
        return select(blocks.c.blocked_id).where(blocks.c.blocker_id == viewer_id).union(
            select(blocks.c.blocker_id).where(blocks.c.blocked_id == viewer_id), self.suspended_ids())

    def friends_of(self, user_id: str) -> Any:
        """A subquery of ``user_id``'s friends' ids: people they follow who follow them back."""
        out, back = follows.alias("out"), follows.alias("back")
        return (select(out.c.followee_id)
                .join(back, and_(back.c.follower_id == out.c.followee_id, back.c.followee_id == user_id))
                .where(out.c.follower_id == user_id))

    def _received(self, viewer_id: str) -> Any:
        """Messages carrying a serve sent to ``viewer_id``, still there, from someone not hidden from them."""
        return (select(messages)
                .join(conversation_members, and_(conversation_members.c.conversation_id == messages.c.conversation_id,
                                                 conversation_members.c.user_id == viewer_id))
                .where(messages.c.sender_id != viewer_id, messages.c.analysis_id.is_not(None),
                       messages.c.deleted_at.is_(None), messages.c.sender_id.not_in(self.hidden_from(viewer_id))))

    def received_serves(self, viewer_id: str, limit: int,
                        before: tuple[datetime, str] | None = None) -> list[dict[str, Any]]:
        """Serves sent to ``viewer_id``, newest first, whether or not they can still open them."""
        query = self._received(viewer_id)
        if before:
            query = query.where(tuple_(messages.c.created_at, messages.c.id) < tuple_(
                bindparam("r_at", before[0], UTCDateTime), bindparam("r_id", before[1])))
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(
                query.order_by(messages.c.created_at.desc(), messages.c.id.desc()).limit(limit)).mappings()]

    def unseen_serves(self, viewer_id: str) -> int:
        """How many serves sent to ``viewer_id`` they haven't opened and still can: the sender's
        own finished analysis, from someone who's a friend now."""
        received = self._received(viewer_id).subquery()
        with self.engine.connect() as conn:
            return conn.execute(
                select(func.count()).select_from(received)
                .join(analyses, and_(analyses.c.id == received.c.analysis_id, analyses.c.user_id == received.c.sender_id))
                .where(received.c.seen_at.is_(None), analyses.c.status == "succeeded",
                       received.c.sender_id.in_(self.friends_of(viewer_id)))).scalar_one()

    def mark_serve_seen(self, analysis_id: str, viewer_id: str) -> int:
        """``viewer_id`` opened ``analysis_id``: every message that sent it to them is now seen."""
        theirs = select(conversation_members.c.conversation_id).where(conversation_members.c.user_id == viewer_id)
        with self.engine.begin() as conn:
            return conn.execute(update(messages).where(
                messages.c.analysis_id == analysis_id, messages.c.sender_id != viewer_id,
                messages.c.seen_at.is_(None), messages.c.conversation_id.in_(theirs)).values(seen_at=now())).rowcount

    def analyses_by_id(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        if not ids:
            return {}
        with self.engine.connect() as conn:
            return {r["id"]: dict(r) for r in conn.execute(select(analyses).where(analyses.c.id.in_(ids))).mappings()}

    def messages_sent_since(self, sender_id: str, since: datetime) -> int:
        with self.engine.connect() as conn:
            return conn.execute(select(func.count()).select_from(messages).where(
                messages.c.sender_id == sender_id, messages.c.created_at >= since)).scalar_one()

    def save_user_report(self, **fields: Any) -> None:
        with self.engine.begin() as conn:
            conn.execute(insert(user_reports).values(created_at=now(), **fields))

    def people_reports(self, since: datetime | None = None, reporter_id: str | None = None) -> list[dict[str, Any]]:
        """Reports of people and messages, oldest first."""
        query = select(user_reports).order_by(user_reports.c.created_at)
        if since:
            query = query.where(user_reports.c.created_at >= since)
        if reporter_id:
            query = query.where(user_reports.c.reporter_id == reporter_id)
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(query).mappings()]

    def delete_old_user_reports(self, before: datetime) -> int:
        with self.engine.begin() as conn:
            return conn.execute(delete(user_reports).where(user_reports.c.created_at < before)).rowcount

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
                   users.c.email_verified_at.label("user_email_verified_at"),
                   users.c.suspended_at.label("user_suspended_at"))
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

    def set_note(self, analysis_id: str, user_id: str, note: str | None) -> bool:
        """Set (or, with None, clear) the owner's note. False if there's no such analysis of theirs."""
        with self.engine.begin() as conn:
            return conn.execute(update(analyses).where(
                analyses.c.id == analysis_id, analyses.c.user_id == user_id).values(note=note)).rowcount == 1

    def set_scores(self, analysis_id: str, overall: int | None, key: dict) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(analyses).where(analyses.c.id == analysis_id)
                         .values(overall_score=overall, key_scores=key))

    def unscored(self, limit: int) -> list[str]:
        """Succeeded analyses that don't have their History scores yet (from before they existed)."""
        query = (select(analyses.c.id).where(analyses.c.status == "succeeded", analyses.c.key_scores.is_(None))
                 .order_by(analyses.c.created_at).limit(limit))
        with self.engine.connect() as conn:
            return list(conn.execute(query).scalars())

    def delete_session(self, token_hash: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(sessions).where(sessions.c.token_hash == token_hash))

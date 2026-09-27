"""Persistence for analysis records (SQLite or Postgres). The table doubles as the job queue."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, insert, select, tuple_, update
from sqlalchemy.engine import make_url

from .tables import analyses

IN_PROGRESS = ("extracting_pose", "analyzing", "rendering")


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

    def create(self, hand: str, filename: str, content_type: str, size_bytes: int) -> dict[str, Any]:
        ts = now()
        row = {
            "id": uuid.uuid4().hex, "hand": hand, "filename": filename,
            "content_type": content_type, "size_bytes": size_bytes,
            "status": "awaiting_upload", "error_code": None, "error_message": None,
            "counts": None, "created_at": ts, "updated_at": ts,
        }
        with self.engine.begin() as conn:
            conn.execute(insert(analyses).values(row))
        return row

    def get(self, analysis_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(analyses).where(analyses.c.id == analysis_id)).mappings().first()
        return dict(row) if row else None

    def list(self, limit: int, before: tuple[datetime, str] | None = None) -> list[dict[str, Any]]:
        """Newest first. ``before`` is a (created_at, id) keyset cursor."""
        query = select(analyses)
        if before:
            query = query.where(tuple_(analyses.c.created_at, analyses.c.id) < tuple_(*before))
        query = query.order_by(analyses.c.created_at.desc(), analyses.c.id.desc()).limit(limit)
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(query).mappings()]

    def transition(self, analysis_id: str, from_statuses: tuple[str, ...], to_status: str) -> bool:
        """Atomically move to ``to_status`` only if currently in ``from_statuses``."""
        with self.engine.begin() as conn:
            result = conn.execute(
                update(analyses)
                .where(analyses.c.id == analysis_id, analyses.c.status.in_(from_statuses))
                .values(status=to_status, error_code=None, error_message=None, updated_at=now())
            )
        return result.rowcount == 1

    def set_status(self, analysis_id: str, status: str, **fields: Any) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                update(analyses).where(analyses.c.id == analysis_id)
                .values(status=status, updated_at=now(), **fields)
            )

    def claim_next(self) -> dict[str, Any] | None:
        """Take the oldest queued job.

        One UPDATE makes the claim atomic. On Postgres, SKIP LOCKED lets
        concurrent workers pass over a row another worker is claiming instead
        of waiting for it; SQLite serialises writers, so it needs neither.
        """
        oldest = (
            select(analyses.c.id).where(analyses.c.status == "queued")
            .order_by(analyses.c.updated_at).limit(1)
            .with_for_update(skip_locked=True).scalar_subquery()
        )
        with self.engine.begin() as conn:
            row = conn.execute(
                update(analyses).where(analyses.c.id == oldest)
                .values(status="extracting_pose", updated_at=now())
                .returning(*analyses.c)
            ).mappings().first()
        return dict(row) if row else None

    def requeue_interrupted(self) -> int:
        """Put jobs a crashed worker left mid-flight back on the queue."""
        with self.engine.begin() as conn:
            result = conn.execute(
                update(analyses).where(analyses.c.status.in_(IN_PROGRESS))
                .values(status="queued", updated_at=now())
            )
        return result.rowcount

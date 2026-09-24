"""SQLite persistence for analysis records. The table doubles as the job queue."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

IN_PROGRESS = ("extracting_pose", "analyzing", "rendering")

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY,
    hand TEXT NOT NULL,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    status TEXT NOT NULL,
    error_code TEXT,
    error_message TEXT,
    counts TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS analyses_status ON analyses (status, updated_at);
CREATE INDEX IF NOT EXISTS analyses_created ON analyses (created_at DESC, id DESC);
"""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def create(self, hand: str, filename: str, content_type: str, size_bytes: int) -> dict[str, Any]:
        ts = now()
        row = {
            "id": uuid.uuid4().hex, "hand": hand, "filename": filename,
            "content_type": content_type, "size_bytes": size_bytes,
            "status": "awaiting_upload", "error_code": None, "error_message": None,
            "counts": None, "created_at": ts, "updated_at": ts,
        }
        with self.connect() as conn:
            conn.execute(
                f"INSERT INTO analyses ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                tuple(row.values()),
            )
        return row

    def get(self, analysis_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
        return dict(row) if row else None

    def list(self, limit: int, before: tuple[str, str] | None = None) -> list[dict[str, Any]]:
        """Newest first. ``before`` is a (created_at, id) keyset cursor."""
        query, params = "SELECT * FROM analyses", []
        if before:
            query += " WHERE (created_at, id) < (?, ?)"
            params += list(before)
        query += " ORDER BY created_at DESC, id DESC LIMIT ?"
        with self.connect() as conn:
            rows = conn.execute(query, (*params, limit)).fetchall()
        return [dict(r) for r in rows]

    def transition(self, analysis_id: str, from_statuses: tuple[str, ...], to_status: str) -> bool:
        """Atomically move to ``to_status`` only if currently in ``from_statuses``."""
        marks = ", ".join("?" * len(from_statuses))
        with self.connect() as conn:
            cur = conn.execute(
                f"UPDATE analyses SET status = ?, error_code = NULL, error_message = NULL, "
                f"updated_at = ? WHERE id = ? AND status IN ({marks})",
                (to_status, now(), analysis_id, *from_statuses),
            )
        return cur.rowcount == 1

    def set_status(self, analysis_id: str, status: str, **fields: Any) -> None:
        if "counts" in fields and fields["counts"] is not None:
            fields["counts"] = json.dumps(fields["counts"])
        assignments = ", ".join(f"{k} = ?" for k in ("status", "updated_at", *fields))
        with self.connect() as conn:
            conn.execute(
                f"UPDATE analyses SET {assignments} WHERE id = ?",
                (status, now(), *fields.values(), analysis_id),
            )

    def claim_next(self) -> dict[str, Any] | None:
        """Take the oldest queued job; the single UPDATE makes the claim atomic."""
        with self.connect() as conn:
            row = conn.execute(
                "UPDATE analyses SET status = 'extracting_pose', updated_at = ? WHERE id = ("
                "SELECT id FROM analyses WHERE status = 'queued' ORDER BY updated_at LIMIT 1"
                ") RETURNING *",
                (now(),),
            ).fetchone()
        return dict(row) if row else None

    def requeue_interrupted(self) -> int:
        """Put jobs a crashed worker left mid-flight back on the queue."""
        marks = ", ".join("?" * len(IN_PROGRESS))
        with self.connect() as conn:
            cur = conn.execute(
                f"UPDATE analyses SET status = 'queued', updated_at = ? WHERE status IN ({marks})",
                (now(), *IN_PROGRESS),
            )
        return cur.rowcount

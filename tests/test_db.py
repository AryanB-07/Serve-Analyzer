"""Database layer: migrations, the job queue and settings. Runs on SQLite, or on Postgres
when SERVE_API_DATABASE_URL is set (see conftest.py)."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect

from serve_api import migrate
from serve_api.db import Database, now
from serve_api.settings import DEV_SECRET, Settings
from serve_api.tables import metadata
from tests.conftest import make_user, production_settings

LEGACY_SCHEMA = """
CREATE TABLE analyses (
    id TEXT PRIMARY KEY, hand TEXT NOT NULL, filename TEXT NOT NULL, content_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL, status TEXT NOT NULL, error_code TEXT, error_message TEXT,
    counts TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX analyses_status ON analyses (status, updated_at);
CREATE INDEX analyses_created ON analyses (created_at DESC, id DESC);
"""


@pytest.fixture
def db(tmp_path) -> Database:
    database = Database(Settings(data_dir=tmp_path).sqlalchemy_url)
    migrate.upgrade(database.engine)
    return database


def test_upgrade_creates_the_schema_and_is_idempotent(tmp_path):
    database = Database(Settings(data_dir=tmp_path).sqlalchemy_url)
    assert not migrate.is_current(database.engine)
    migrate.upgrade(database.engine)
    migrate.upgrade(database.engine)
    assert migrate.is_current(database.engine)
    assert "analyses" in inspect(database.engine).get_table_names()


def test_migrations_match_the_table_definitions(db):
    """Fails when tables.py changes without a new migration."""
    with db.engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), metadata)
    assert diff == []


def test_a_database_from_before_migrations_is_converted_in_place(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.executescript(LEGACY_SCHEMA)
        conn.execute(
            "INSERT INTO analyses VALUES (?, 'right', 'a.mp4', 'video/mp4', 10, 'succeeded', NULL, NULL, ?, ?, ?)",
            ("abc", json.dumps({"good": 3, "borderline": 1, "off": 0, "unknown": 2}),
             "2026-09-27T01:28:10.506+00:00", "2026-09-27T01:28:23.100+00:00"),
        )
    database = Database(f"sqlite:///{path}")
    migrate.upgrade(database.engine)
    row = database.get("abc")
    assert row["counts"] == {"good": 3, "borderline": 1, "off": 0, "unknown": 2}
    assert row["created_at"].tzinfo is not None
    assert row["created_at"].isoformat() == "2026-09-27T01:28:10.506000+00:00"
    assert "analyses_legacy" not in inspect(database.engine).get_table_names()


def test_timestamps_round_trip_as_utc_and_listing_pages_by_cursor(db):
    user = make_user(db)
    ids = [db.create(user, "right", f"{i}.mp4", "video/mp4", 10)["id"] for i in range(3)]
    row = db.get(ids[0])
    assert row["created_at"].utcoffset() == timedelta(0)
    assert abs(now() - row["created_at"]) < timedelta(minutes=1)
    first = db.list(user, 2)
    assert [r["id"] for r in first] == ids[::-1][:2]
    rest = db.list(user, 2, (first[-1]["created_at"], first[-1]["id"]))
    assert [r["id"] for r in rest] == [ids[0]]


def test_counts_are_stored_as_json(db):
    created = db.create(make_user(db), "right", "a.mp4", "video/mp4", 10)
    db.set_status(created["id"], "succeeded", counts={"good": 1, "borderline": 0, "off": 2, "unknown": 0})
    assert db.get(created["id"])["counts"]["off"] == 2


def test_concurrent_workers_never_claim_the_same_job(db):
    user = make_user(db)
    for i in range(3):
        job = db.create(user, "right", f"{i}.mp4", "video/mp4", 10)
        assert db.transition(job["id"], ("awaiting_upload",), "queued")
    with ThreadPoolExecutor(8) as pool:
        claims = [c for c in pool.map(lambda i: db.claim_next(f"worker-{i}"), range(8)) if c]
    assert len(claims) == 3
    assert len({c["id"] for c in claims}) == 3
    assert all(c["status"] == "extracting_pose" for c in claims)
    assert len({c["claim_token"] for c in claims}) == 3


def test_the_worker_refuses_an_out_of_date_schema(tmp_path):
    database = Database(Settings(data_dir=tmp_path).sqlalchemy_url)
    with pytest.raises(RuntimeError, match="out of date"):
        migrate.wait_until_current(database.engine, timeout_s=0)


def test_settings_require_a_real_secret_and_email_outside_development(tmp_path):
    Settings(data_dir=tmp_path, environment="development", secret=DEV_SECRET).check()
    with pytest.raises(RuntimeError, match="SERVE_API_SECRET"):
        production_settings(tmp_path, secret=DEV_SECRET).check()
    with pytest.raises(RuntimeError, match="SERVE_API_SMTP_HOST"):
        production_settings(tmp_path, smtp_host="").check()
    with pytest.raises(RuntimeError, match="SERVE_API_APP_URL"):
        production_settings(tmp_path, app_url="http://localhost:5173").check()
    production_settings(tmp_path).check()


def test_postgres_urls_use_the_psycopg_driver(tmp_path):
    for url in ("postgres://u:p@h/db", "postgresql://u:p@h/db"):
        assert Settings(data_dir=tmp_path, database_url=url).sqlalchemy_url == "postgresql+psycopg://u:p@h/db"
    assert Settings(data_dir=tmp_path, database_url="").sqlalchemy_url.startswith("sqlite:///")

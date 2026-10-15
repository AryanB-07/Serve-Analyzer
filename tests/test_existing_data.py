"""Data that's already in a database keeps working: rows from older versions, odd values, and the
seed data for trying the app by hand (scripts/seed_dev_data.py, scripts/check_dev_data.py)."""

import json
import sys
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import MetaData, Table, insert, update

from serve_api import keys, migrate, worker
from serve_api.db import Database, now
from serve_api.settings import Settings
from serve_api.storage import LocalStorage
from serve_api.tables import analyses
from tests.test_account import app, client, db_of, mailer, settings, signup, verify  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
def schema_2_results() -> dict:
    """A results file as the pipeline wrote it at schema 2: no camera_view, quality, confidence,
    plain feedback or scores (the oldest real files in development databases). Built from the
    demo serve's real output."""
    shown = json.loads((ROOT / "frontend/public/mock/demo-serve-1/result.json").read_text())
    stored = ("hand", "fps", "n_frames", "width", "height", "phases", "metrics", "labels", "ranges", "warnings")
    return {"schema_version": 2, **{k: shown[k] for k in stored}, "outputs": {},
            "feedback": [{k: f[k] for k in ("text", "phase", "metric", "status")} for f in shown["feedback"]]}


@pytest.fixture
def me(client, mailer):
    verify(client, mailer, signup(client))
    return client


def _finished(app, settings, client, results, **fields):
    analysis_id = client.post("/analyses", json={"hand": "right", "filename": "old.mp4", "content_type": "video/mp4",
                                                 "size_bytes": 1}).json()["analysis"]["id"]
    path = LocalStorage(settings).path(keys.output_key(analysis_id, keys.RESULTS))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results))
    with db_of(app).engine.begin() as conn:
        conn.execute(update(analyses).where(analyses.c.id == analysis_id).values(status="succeeded", **fields))
    return analysis_id


def test_a_schema_2_result_still_loads_and_is_scored_by_housekeeping(app, settings, me):
    analysis_id = _finished(app, settings, me, schema_2_results(), counts={"good": 2, "borderline": 1, "off": 0, "unknown": 0})
    assert me.get("/analyses").json()["items"][0]["overall_score"] is None  # not scored yet
    result = me.get(f"/analyses/{analysis_id}/result")
    assert result.status_code == 200
    body = result.json()
    assert body["camera_view"] is None and body["quality"] is None and body["confidence"] is None
    assert body["feedback"][0]["plain"] is None

    worker.backfill_scores(db_of(app), LocalStorage(settings))
    summary = me.get("/analyses").json()["items"][0]
    assert summary["overall_score"] is not None
    assert set(summary["key_scores"]) == {"front_knee_flexion", "back_knee_flexion", "trunk_tilt", "elbow_angle", "wrist_height"}
    assert me.get("/analyses", params={"min_score": 0}).json()["items"][0]["id"] == analysis_id


def test_an_error_code_this_version_doesnt_know_doesnt_break_history(app, me):
    """Say a code was renamed, or a newer worker wrote it mid-deploy: one row mustn't take down
    History, the analysis page or the data download."""
    analysis_id = me.post("/analyses", json={"hand": "right", "filename": "x.mp4", "content_type": "video/mp4",
                                             "size_bytes": 1}).json()["analysis"]["id"]
    db_of(app).set_status(analysis_id, "failed", error_code="A_CODE_FROM_THE_FUTURE",
                          error_message="/srv/app/secret/path.py exploded")
    for path in ("/analyses", f"/analyses/{analysis_id}", "/auth/me/export"):
        assert me.get(path).status_code == 200, path
    error = me.get(f"/analyses/{analysis_id}").json()["error"]
    assert error["code"] == "INTERNAL"
    assert "/srv" not in error["message"]  # the generic message, not whatever was stored
    assert me.get("/auth/me/export").json()["analyses"][0]["error"]["code"] == "INTERNAL"


def test_a_database_with_data_from_0007_upgrades_and_works(tmp_path):
    """The last schema before camera positions, scores and notes, with rows in it."""
    settings = Settings(data_dir=tmp_path)  # SQLite, or the test Postgres (conftest.py)
    db = Database(settings.sqlalchemy_url)
    command.upgrade(migrate.alembic_config(settings.sqlalchemy_url), "0007")
    user = db.create_user("old@example.com", "hash")
    old_analyses = Table("analyses", MetaData(), autoload_with=db.engine)  # the table as 0007 left it
    with db.engine.begin() as conn:
        conn.execute(insert(old_analyses).values(
            id="a1", user_id=user["id"], hand="right", filename="old.mp4", content_type="video/mp4", size_bytes=1,
            status="succeeded", counts={"good": 2, "borderline": 1, "off": 0, "unknown": 0},
            created_at=now(), updated_at=now(), attempts=0))
    path = LocalStorage(settings).path(keys.output_key("a1", keys.RESULTS))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(schema_2_results()))

    migrate.upgrade(db.engine)
    assert migrate.is_current(db.engine)
    row = db.get("a1")
    assert row["camera_view"] is None and row["note"] is None and row["overall_score"] is None
    assert db.unscored(10) == ["a1"]  # an old row's key_scores is SQL NULL, so backfill finds it
    assert worker.backfill_scores(db, LocalStorage(settings)) == 1
    assert db.get("a1")["overall_score"] is not None
    assert db.list(user["id"], 10)[0]["id"] == "a1"


@pytest.mark.integration
def test_the_seed_data_loads_everywhere(tmp_path, monkeypatch):
    """The seed script's accounts, checked page by page through the API (runs the pipeline once)."""
    monkeypatch.setenv("SERVE_API_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SERVE_API_DATABASE_URL", raising=False)
    sys.path.insert(0, str(ROOT / "scripts"))
    import check_dev_data
    import seed_dev_data

    monkeypatch.setattr(sys, "argv", ["seed_dev_data.py"])
    seed_dev_data.main()
    assert check_dev_data.main() == 0
    # Seeding again replaces the seed accounts instead of failing or doubling them.
    seed_dev_data.main()
    seeder = seed_dev_data.Seeder(Settings())
    assert len(seeder.seed_user_ids()) == 5
    seeder.remove()
    assert seeder.seed_user_ids() == []

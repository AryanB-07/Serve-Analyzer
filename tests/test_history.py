"""History: scores saved with each analysis, the sidebar's filters, and your own notes."""

import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from serve_analyzer.reference import load_ranges, ranges_to_dict
from serve_api import keys, worker
from serve_api.db import now
from serve_api.storage import LocalStorage
from serve_api.tables import analyses
from tests.test_account import app, client, db_of, mailer, settings, signup, verify  # noqa: F401

RANGES = ranges_to_dict(load_ranges())


def _analysis(app, settings, client, *, knee=None, height=None, trunk=None, age_days=0.0, status="succeeded"):
    """A finished analysis with the given key measurements, scored the way the worker does it."""
    analysis_id = client.post("/analyses", json={"hand": "right", "filename": "s.mp4", "content_type": "video/mp4",
                                                 "size_bytes": 1}).json()["analysis"]["id"]
    results = {"labels": {}, "ranges": RANGES,
               "metrics": {"trophy": {"front_knee_flexion": knee, "trunk_tilt": trunk}, "contact": {"wrist_height": height}}}
    storage = LocalStorage(settings)
    path = storage.path(keys.output_key(analysis_id, keys.RESULTS))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results))
    db = db_of(app)
    with db.engine.begin() as conn:
        conn.execute(update(analyses).where(analyses.c.id == analysis_id).values(
            status=status, created_at=now() - timedelta(days=age_days)))
    if status == "succeeded":
        worker.backfill_scores(db, storage)
    return analysis_id


def _list(client, **params):
    res = client.get("/analyses", params=params)
    assert res.status_code == 200, res.text
    return res.json()


def _ids(client, **params):
    return [a["id"] for a in _list(client, **params)["items"]]


@pytest.fixture
def me(app, client, mailer):
    verify(client, mailer, signup(client))
    return client


# --- scores --------------------------------------------------------------------------------------

def test_a_finished_analysis_carries_its_scores(app, settings, me):
    analysis_id = _analysis(app, settings, me, knee=65.0, height=1.45)
    summary = _list(me)["items"][0]
    assert summary["id"] == analysis_id
    assert summary["key_scores"]["front_knee_flexion"] == {"phase": "trophy", "value": 65.0, "score": 100, "band": "good"}
    assert summary["key_scores"]["back_knee_flexion"] is None
    assert summary["overall_score"] == round((100 + summary["key_scores"]["wrist_height"]["score"]) / 2)


def test_the_worker_saves_the_scores_from_the_pipeline(app, me, settings, monkeypatch):
    analysis_id = me.post("/analyses", json={"hand": "right", "filename": "s.mp4", "content_type": "video/mp4",
                                             "size_bytes": 1}).json()["analysis"]["id"]
    storage = LocalStorage(settings)
    path = storage.path(keys.input_key(analysis_id, "video/mp4"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    db = db_of(app)
    db.transition(analysis_id, ("awaiting_upload",), "queued")
    scores = {"overall": 77, "key": {"trunk_tilt": {"phase": "trophy", "value": 25.0, "score": 100, "band": "good"}}}

    def fake(video, hand, out_dir, on_stage, **kwargs):
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / keys.RESULTS).write_text(json.dumps({"labels": {}, "scores": scores}))
        return type("R", (), {"phases": type("P", (), {"contact": 1})()})()

    monkeypatch.setattr(worker, "analyze", fake)
    worker.process(db.claim_next("w"), db, storage, "w")
    row = db.get(analysis_id)
    assert row["overall_score"] == 77 and row["key_scores"] == scores["key"]


def test_older_analyses_are_scored_once_by_housekeeping(app, settings, me):
    analysis_id = me.post("/analyses", json={"hand": "right", "filename": "s.mp4", "content_type": "video/mp4",
                                             "size_bytes": 1}).json()["analysis"]["id"]
    db, storage = db_of(app), LocalStorage(settings)
    db.set_status(analysis_id, "succeeded")  # no results file: it can't be scored
    assert db.unscored(10) == [analysis_id]
    assert worker.backfill_scores(db, storage) == 1
    assert db.unscored(10) == []  # recorded as unscorable, not retried every hour
    assert db.get(analysis_id)["overall_score"] is None


# --- filters -------------------------------------------------------------------------------------

def test_filtering_by_upload_time(app, settings, me):
    old = _analysis(app, settings, me, knee=65.0, age_days=40)
    recent = _analysis(app, settings, me, knee=65.0, age_days=2)
    week_ago = (now() - timedelta(days=7)).isoformat()
    assert _ids(me, uploaded_from=week_ago) == [recent]
    assert _ids(me, uploaded_to=week_ago) == [old]
    assert _ids(me) == [recent, old]


def test_filtering_by_overall_score(app, settings, me):
    good = _analysis(app, settings, me, knee=65.0)        # 100
    borderline = _analysis(app, settings, me, knee=90.0)  # 60
    off = _analysis(app, settings, me, knee=10.0)         # 0
    unscored = _analysis(app, settings, me, status="failed")
    assert _ids(me, min_score=80) == [good]
    assert _ids(me, min_score=50, max_score=79) == [borderline]
    assert _ids(me, max_score=49) == [off]
    assert unscored in _ids(me)  # without a score filter everything shows


def test_filtering_by_a_key_positions_band(app, settings, me):
    bent = _analysis(app, settings, me, knee=10.0, trunk=25.0)
    fine = _analysis(app, settings, me, knee=65.0, trunk=25.0)
    assert _ids(me, stat="front_knee_flexion", stat_band="off") == [bent]
    assert _ids(me, stat="front_knee_flexion", stat_band="good") == [fine]
    assert set(_ids(me, stat="trunk_tilt", stat_band="good")) == {bent, fine}
    assert _ids(me, stat="back_knee_flexion", stat_band="good") == []  # never measured


def test_filters_combine_and_page(app, settings, me):
    made = [_analysis(app, settings, me, knee=65.0, age_days=i * 0.1) for i in range(5)]
    _analysis(app, settings, me, knee=10.0)
    first = _list(me, min_score=80, limit=2)
    assert [a["id"] for a in first["items"]] == made[:2]
    second = _list(me, min_score=80, limit=2, cursor=first["next_cursor"])
    assert [a["id"] for a in second["items"]] == made[2:4]


@pytest.mark.parametrize("params", [
    {"stat": "front_knee_flexion"}, {"stat_band": "good"}, {"stat": "elbow_wobble", "stat_band": "good"},
    {"min_score": 101}, {"uploaded_from": "yesterday"},
])
def test_bad_filters_are_refused(me, params):
    assert me.get("/analyses", params=params).status_code == 422


def test_filters_never_show_someone_elses_analyses(app, settings, me):
    _analysis(app, settings, me, knee=65.0)
    other = TestClient(app)
    signup(other)
    assert other.get("/analyses", params={"min_score": 0}).json()["items"] == []


# --- notes ---------------------------------------------------------------------------------------

def test_a_note_can_be_added_changed_and_removed(app, settings, me):
    analysis_id = _analysis(app, settings, me, knee=65.0)
    res = me.put(f"/analyses/{analysis_id}/note", json={"note": "  New grip, windy day  "})
    assert res.status_code == 200 and res.json()["note"] == "New grip, windy day"
    assert _list(me)["items"][0]["note"] == "New grip, windy day"
    assert me.get(f"/analyses/{analysis_id}").json()["note"] == "New grip, windy day"
    assert me.put(f"/analyses/{analysis_id}/note", json={"note": "   "}).json()["note"] is None
    assert me.put(f"/analyses/{analysis_id}/note", json={}).json()["note"] is None


def test_notes_have_a_length_limit_and_belong_to_their_owner(app, settings, me):
    analysis_id = _analysis(app, settings, me, knee=65.0)
    assert me.put(f"/analyses/{analysis_id}/note", json={"note": "x" * 1001}).status_code == 422
    stranger = TestClient(app)
    signup(stranger)
    assert stranger.put(f"/analyses/{analysis_id}/note", json={"note": "mine now"}).status_code == 404
    assert me.put("/analyses/nope/note", json={"note": "x"}).status_code == 404


def test_the_data_download_includes_notes(app, settings, me):
    analysis_id = _analysis(app, settings, me, knee=65.0)
    me.put(f"/analyses/{analysis_id}/note", json={"note": "Felt good"})
    assert me.get("/auth/me/export").json()["analyses"][0]["note"] == "Felt good"

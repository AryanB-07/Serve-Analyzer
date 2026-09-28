"""The job queue under several workers, and per-user limits."""

import json
import threading
import time
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from serve_api import keys, migrate, worker
from serve_api.app import create_app
from serve_api.db import Database, now
from serve_api.settings import Settings
from serve_api.storage import LocalStorage
from serve_api.tables import analyses
from tests.conftest import make_user, sign_in

LEASE = timedelta(minutes=2)
FAILED_MESSAGE = "Something went wrong while analysing this video."


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path, secret="test", public_base="")


@pytest.fixture
def db(settings) -> Database:
    database = Database(settings.sqlalchemy_url)
    migrate.upgrade(database.engine)
    return database


def queued_job(db: Database, user: str | None = None) -> str:
    job = db.create(user or make_user(db), "right", "a.mp4", "video/mp4", 10)
    assert db.transition(job["id"], ("awaiting_upload",), "queued")
    return job["id"]


def age_heartbeat(db: Database, analysis_id: str, by: timedelta) -> None:
    with db.engine.begin() as conn:
        conn.execute(update(analyses).where(analyses.c.id == analysis_id)
                     .values(heartbeat_at=now() - by))


# --- claims -------------------------------------------------------------------------

def test_a_claim_records_its_token_heartbeat_and_attempt(db):
    job_id = queued_job(db)
    claimed = db.claim_next("worker-a")
    assert claimed["id"] == job_id and claimed["claim_token"] == "worker-a"
    assert claimed["attempts"] == 1
    assert abs(claimed["heartbeat_at"] - now()) < timedelta(seconds=5)


def test_only_the_claim_holder_can_write_and_finishing_releases_the_claim(db):
    job_id = queued_job(db)
    db.claim_next("worker-a")
    assert not db.update_claimed(job_id, "someone-else", "succeeded")
    assert db.get(job_id)["status"] == "extracting_pose"
    assert db.update_claimed(job_id, "worker-a", "analyzing")
    assert db.get(job_id)["claim_token"] == "worker-a"
    assert db.update_claimed(job_id, "worker-a", "succeeded", counts={"good": 1})
    row = db.get(job_id)
    assert row["status"] == "succeeded" and row["claim_token"] is None
    assert not db.heartbeat(job_id, "worker-a")  # nothing left to keep alive


def test_live_claims_are_left_alone_and_abandoned_ones_requeued(db):
    alive, dead = queued_job(db), queued_job(db)
    db.claim_next("worker-a")
    db.claim_next("worker-b")
    age_heartbeat(db, dead, LEASE + timedelta(seconds=1))
    assert db.release_stale(LEASE, 3, FAILED_MESSAGE) == (1, 0)
    assert db.get(alive)["status"] == "extracting_pose"
    requeued = db.get(dead)
    assert requeued["status"] == "queued" and requeued["claim_token"] is None


def test_the_old_worker_cannot_overwrite_the_one_that_took_over(db):
    job_id = queued_job(db)
    db.claim_next("slow-worker")
    age_heartbeat(db, job_id, LEASE * 2)
    db.release_stale(LEASE, 3, FAILED_MESSAGE)
    assert db.claim_next("new-worker")["attempts"] == 2
    assert not db.heartbeat(job_id, "slow-worker")
    assert not db.update_claimed(job_id, "slow-worker", "failed", error_code="INTERNAL")
    assert db.update_claimed(job_id, "new-worker", "succeeded")
    assert db.get(job_id)["status"] == "succeeded"


def test_a_job_that_keeps_killing_workers_is_failed_after_three_attempts(db):
    job_id = queued_job(db)
    for attempt in range(1, 4):
        assert db.claim_next(f"worker-{attempt}")["attempts"] == attempt
        age_heartbeat(db, job_id, LEASE * 2)  # the worker died mid-job
        requeued, failed = db.release_stale(LEASE, 3, FAILED_MESSAGE)
    assert (requeued, failed) == (0, 1)
    row = db.get(job_id)
    assert row["status"] == "failed" and row["error_code"] == "INTERNAL"
    assert row["error_message"] == FAILED_MESSAGE
    assert db.claim_next("worker-4") is None


# --- the worker process -------------------------------------------------------------

def fake_analyze(duration_s: float, during=None):
    """Stands in for the pipeline: reports stages, takes a while, writes results.json."""

    def analyze(video, hand, out_dir, on_stage):
        for stage in ("extracting_pose", "analyzing", "rendering"):
            on_stage(stage)
            time.sleep(duration_s / 3)
            if during and stage == "analyzing":
                during()
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / keys.RESULTS).write_text(json.dumps({"labels": {"trophy": {"elbow_angle": "good"}}}))
        return SimpleNamespace(phases=SimpleNamespace(contact=1))

    return analyze


def test_the_heartbeat_keeps_a_slow_job_claimed(db, settings, monkeypatch):
    job_id = queued_job(db)
    job = db.claim_next("worker-a")
    beats = []
    real_heartbeat = db.heartbeat
    monkeypatch.setattr(db, "heartbeat", lambda *a: beats.append(time.monotonic()) or real_heartbeat(*a))
    monkeypatch.setattr(worker, "analyze", fake_analyze(0.6))
    worker.process(job, db, LocalStorage(settings), "worker-a", heartbeat_every=timedelta(seconds=0.1))
    assert len(beats) >= 3
    row = db.get(job_id)
    assert row["status"] == "succeeded" and row["counts"]["good"] == 1


def test_a_worker_that_lost_its_claim_discards_its_result(db, settings, monkeypatch):
    job_id = queued_job(db)
    job = db.claim_next("slow-worker")

    def taken_over():
        age_heartbeat(db, job_id, LEASE * 2)
        db.release_stale(LEASE, 3, FAILED_MESSAGE)
        db.claim_next("new-worker")

    monkeypatch.setattr(worker, "analyze", fake_analyze(0.1, during=taken_over))
    worker.process(job, db, LocalStorage(settings), "slow-worker")
    row = db.get(job_id)  # still exactly as the new worker's claim left it
    assert row["claim_token"] == "new-worker" and row["status"] == "extracting_pose"
    assert row["attempts"] == 2 and row["counts"] is None


def test_two_workers_share_the_queue_without_overlap(db, settings, monkeypatch):
    jobs = {queued_job(db) for _ in range(6)}
    processed: list[str] = []
    lock = threading.Lock()
    real_process = worker.process

    def counting_process(job, *args, **kwargs):
        with lock:
            processed.append(job["id"])
        real_process(job, *args, **kwargs)

    monkeypatch.setattr(worker, "analyze", fake_analyze(0.03))
    monkeypatch.setattr(worker, "process", counting_process)
    threads = [threading.Thread(target=worker.run, args=(settings,), kwargs={"poll_s": 0.01, "once": True})
               for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(processed) == sorted(jobs)  # each job exactly once
    assert all(db.get(j)["status"] == "succeeded" for j in jobs)


# --- per-user limits ------------------------------------------------------------------

def create(client: TestClient) -> TestClient:
    return client.post("/analyses", json={
        "hand": "right", "filename": "a.mp4", "content_type": "video/mp4", "size_bytes": 5,
    })


def create_and_upload(client: TestClient) -> str:
    created = create(client).json()
    target = created["upload"]
    assert client.put(target["url"], content=b"video", headers=target["headers"]).status_code == 204
    return created["analysis"]["id"]


def test_each_user_has_a_daily_analysis_budget(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, secret="t", public_base="", daily_analysis_limit=2))
    alice, bob = sign_in(TestClient(app)), sign_in(TestClient(app))
    assert create(alice).status_code == 201
    assert create(alice).status_code == 201
    refused = create(alice)
    assert refused.status_code == 429
    assert refused.json()["detail"] == "You can analyze up to 2 serves a day. Try again tomorrow."
    assert create(bob).status_code == 201  # budgets are per user
    db = app.state.auth.db
    with db.engine.begin() as conn:  # a day later, the old ones no longer count
        conn.execute(update(analyses).values(created_at=now() - timedelta(days=1, minutes=1)))
    assert create(alice).status_code == 201


def test_each_user_can_only_have_so_many_analyses_in_progress(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, secret="t", public_base="", max_active_analyses=1))
    alice, bob = sign_in(TestClient(app)), sign_in(TestClient(app))
    first, second = create_and_upload(alice), create_and_upload(alice)
    assert alice.post(f"/analyses/{first}/start").status_code == 202
    refused = alice.post(f"/analyses/{second}/start")
    assert refused.status_code == 429
    assert "already have 1 analysis in progress" in refused.json()["detail"]
    assert alice.get(f"/analyses/{second}").json()["status"] == "awaiting_upload"
    assert bob.post(f"/analyses/{create_and_upload(bob)}/start").status_code == 202

    db = app.state.auth.db
    db.set_status(first, "failed", error_code="INTERNAL", error_message="x")
    assert alice.post(f"/analyses/{second}/start").status_code == 202  # the slot freed up
    assert alice.post(f"/analyses/{first}/retry").status_code == 429  # and is taken again


def test_retrying_gives_the_job_fresh_attempts(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, secret="t", public_base=""))
    alice = sign_in(TestClient(app))
    analysis_id = create_and_upload(alice)
    alice.post(f"/analyses/{analysis_id}/start")
    db = app.state.auth.db
    db.set_status(analysis_id, "failed", error_code="INTERNAL", error_message="x", attempts=3)
    assert alice.post(f"/analyses/{analysis_id}/retry").status_code == 202
    assert db.get(analysis_id)["attempts"] == 0

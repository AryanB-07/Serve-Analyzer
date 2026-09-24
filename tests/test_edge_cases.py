"""Edge cases across the pipeline and API that the main tests don't cover."""

import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from serve_analyzer import angles as A
from serve_analyzer.config import AnalysisConfig
from serve_analyzer.export import build_frames_payload
from serve_analyzer.models import Hand, PhaseFrames, PoseSequence
from serve_analyzer.phases import detect_contact, detect_phases, detect_racket_drop, detect_trophy
from serve_analyzer.pipeline import analyze_sequence
from serve_analyzer.preprocessing import clean, interpolate_gaps, smooth_series
from serve_analyzer.reference import load_ranges
from serve_api.app import create_app
from serve_api.db import Database
from serve_api.settings import Settings
from serve_api.storage import LocalStorage

nan = np.nan


# --- pipeline ---------------------------------------------------------------

def _standing(frames: int, width: int = 640, height: int = 480) -> PoseSequence:
    lm = np.full((frames, 33, 3), nan)
    pts = {0: (320, 60), 11: (300, 120), 12: (340, 120), 13: (290, 180), 14: (350, 180),
           15: (285, 240), 16: (355, 240), 23: (305, 260), 24: (335, 260), 25: (305, 360),
           26: (335, 360), 27: (305, 450), 28: (335, 450)}
    for j, (x, y) in pts.items():
        lm[:, j] = (x, y, 0.99)
    return PoseSequence(lm, 30.0, width, height)


def test_clip_shorter_than_the_smoothing_window_still_analyses():
    seq = _standing(3)
    out = analyze_sequence(seq, Hand.RIGHT, AnalysisConfig(), load_ranges())
    assert out.result.n_frames == 3
    assert out.result.feedback  # always at least one point


def test_interpolation_and_smoothing_of_all_missing_series():
    s = np.full(10, nan)
    assert np.isnan(interpolate_gaps(s, 5)).all()
    assert np.isnan(smooth_series(s, 5, 2)).all()
    assert interpolate_gaps(np.array([]), 5).size == 0


def test_detectors_handle_all_missing_inputs():
    empty = np.full(20, nan)
    assert detect_contact(empty) is None
    assert detect_trophy(empty, empty, contact=10) is None
    assert detect_racket_drop(empty, trophy=2, contact=10) is None
    assert detect_trophy(np.arange(20.0), np.ones(20), contact=0) is None


def test_phases_on_a_person_who_never_moves():
    seq = clean(_standing(30), 0.5, 5, 150)
    phases = detect_phases(A.compute_series(seq, Hand.RIGHT))
    # A flat wrist trace still yields a contact frame (the first maximum), but
    # the toss arm is never raised, so there is no trophy or racket drop.
    assert phases.contact is not None
    assert phases.trophy is None and phases.racket_drop is None


def test_frames_payload_for_a_portrait_clip_with_missing_frames():
    raw = _standing(4, width=270, height=480)
    raw.landmarks[2, :, :2] = nan
    raw.landmarks[2, :, 2] = 0.0
    smoothed = clean(raw, 0.5, 0, None)
    series = A.compute_series(smoothed, Hand.RIGHT)
    payload = build_frames_payload(raw, smoothed, series, PhaseFrames())
    nose = payload["landmarks"]["raw"]["nose"]
    assert nose["x"][0] == round(320 / 270, 4)  # off-frame x can exceed 1
    assert nose["x"][2] is None and nose["v"][2] == 0.0
    assert payload["landmarks"]["smoothed"]["nose"]["y"][2] is None
    assert all(v is None for v in (payload["series"][m][2] for m in A.METRIC_NAMES))


# --- API and storage -----------------------------------------------------------

@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path, secret="t", public_base="", max_upload_bytes=1000)


@pytest.fixture
def client(settings) -> TestClient:
    return TestClient(create_app(settings))


def _create(client: TestClient, size: int = 10) -> dict:
    return client.post("/analyses", json={
        "hand": "left", "filename": "a.mov", "content_type": "video/quicktime", "size_bytes": size,
    }).json()


def test_upload_url_is_closed_once_the_analysis_starts(client):
    created = _create(client)
    target, analysis_id = created["upload"], created["analysis"]["id"]
    assert client.put(target["url"], content=b"video", headers=target["headers"]).status_code == 204
    assert client.put(target["url"], content=b"again", headers=target["headers"]).status_code == 204
    client.post(f"/analyses/{analysis_id}/start")
    assert client.put(target["url"], content=b"swap", headers=target["headers"]).status_code == 409


def test_upload_rejects_bodies_over_the_limit_and_leaves_no_file(client, settings):
    created = _create(client)
    target = created["upload"]
    res = client.put(target["url"], content=b"x" * 2000, headers=target["headers"])
    assert res.status_code == 413
    assert not list(settings.objects_dir.rglob("input*"))
    assert client.post(f"/analyses/{created['analysis']['id']}/start").status_code == 409


def test_expired_and_tampered_urls_are_refused(settings, client):
    storage = LocalStorage(settings)
    key = "analyses/x/playback.mp4"
    storage.path(key).parent.mkdir(parents=True)
    storage.path(key).write_bytes(b"data")
    url = storage.presign("GET", key)[0]
    assert client.get(url).status_code == 200
    past = int(time.time()) - 1
    assert client.get(f"/storage/{key}", params={"expires": past, "sig": storage._signature("GET", key, past, "")}).status_code == 403
    assert client.get(url.replace("playback", "annotated")).status_code == 403


def test_download_urls_are_stable_within_the_hour(settings):
    storage = LocalStorage(settings)
    assert storage.presign("GET", "a/b.mp4") == storage.presign("GET", "a/b.mp4")
    expires = storage.presign("GET", "a/b.mp4")[1]
    assert expires % 3600 == 0 and expires - time.time() >= settings.download_url_ttl_s


def test_list_rejects_malformed_cursors_and_limits(client):
    assert client.get("/analyses", params={"cursor": "!!!"}).status_code == 400
    assert client.get("/analyses", params={"limit": 0}).status_code == 422
    assert client.get("/analyses", params={"limit": 101}).status_code == 422


def test_worker_requeues_jobs_left_mid_flight(settings):
    db = Database(settings.db_path)
    stuck = db.create("right", "a.mp4", "video/mp4", 10)
    db.set_status(stuck["id"], "extracting_pose")
    waiting = db.create("right", "b.mp4", "video/mp4", 10)
    assert db.requeue_interrupted() == 1
    assert db.get(stuck["id"])["status"] == "queued"
    assert db.get(waiting["id"])["status"] == "awaiting_upload"
    claimed = db.claim_next()
    assert claimed["id"] == stuck["id"] and claimed["status"] == "extracting_pose"
    assert db.claim_next() is None

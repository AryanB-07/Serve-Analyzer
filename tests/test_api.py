from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from serve_analyzer.angles import METRIC_NAMES
from serve_analyzer.landmarks import DRAWN_LANDMARKS
from serve_analyzer.metrics import PHASE_NAMES
from serve_api import schemas
from serve_api.app import create_app
from serve_api.settings import Settings
from serve_api.worker import run

CLIP = Path(__file__).parent / "fixtures" / "sample_serve.mp4"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path, secret="test", public_base="")


@pytest.fixture
def client(settings) -> TestClient:
    return TestClient(create_app(settings))


def create(client: TestClient, size: int = 1000, content_type: str = "video/mp4") -> dict:
    res = client.post("/analyses", json={
        "hand": "right", "filename": "serve.mp4", "content_type": content_type, "size_bytes": size,
    })
    assert res.status_code == 201, res.text
    return res.json()


def upload(client: TestClient, created: dict, body: bytes) -> None:
    target = created["upload"]
    res = client.put(target["url"], content=body, headers=target["headers"])
    assert res.status_code == 204, res.text


def test_schema_literals_match_pipeline():
    assert set(schemas.PhaseName.__args__) == set(PHASE_NAMES)
    assert set(schemas.MetricName.__args__) == set(METRIC_NAMES)
    assert schemas.LANDMARK_NAMES == list(DRAWN_LANDMARKS)


def test_create_returns_presigned_put(client):
    created = create(client)
    assert created["analysis"]["status"] == "awaiting_upload"
    assert created["upload"]["method"] == "PUT"
    assert created["upload"]["headers"] == {"Content-Type": "video/mp4"}
    assert "sig=" in created["upload"]["url"]


def test_create_rejects_oversized_and_bad_type(client):
    too_big = client.post("/analyses", json={
        "hand": "right", "filename": "a.mp4", "content_type": "video/mp4", "size_bytes": 10**10,
    })
    assert too_big.status_code == 413
    bad_type = client.post("/analyses", json={
        "hand": "right", "filename": "a.avi", "content_type": "video/x-msvideo", "size_bytes": 10,
    })
    assert bad_type.status_code == 422


def test_upload_rejects_tampered_signature_and_wrong_content_type(client):
    created = create(client)
    url = created["upload"]["url"]
    assert client.put(url.replace("sig=", "sig=0"), content=b"x",
                      headers={"Content-Type": "video/mp4"}).status_code == 403
    assert client.put(url, content=b"x",
                      headers={"Content-Type": "video/quicktime"}).status_code == 403


def test_start_requires_upload_and_only_once(client):
    created = create(client)
    analysis_id = created["analysis"]["id"]
    assert client.post(f"/analyses/{analysis_id}/start").status_code == 409
    upload(client, created, b"not really a video")
    res = client.post(f"/analyses/{analysis_id}/start")
    assert res.status_code == 202 and res.json()["status"] == "queued"
    assert client.post(f"/analyses/{analysis_id}/start").status_code == 409


def test_unknown_and_unfinished_analyses(client):
    assert client.get("/analyses/nope").status_code == 404
    analysis_id = create(client)["analysis"]["id"]
    assert client.get(f"/analyses/{analysis_id}/result").status_code == 409
    assert client.get(f"/analyses/{analysis_id}/frames").status_code == 409


def test_unreadable_upload_fails_with_code_then_can_retry(client, settings):
    created = create(client)
    analysis_id = created["analysis"]["id"]
    upload(client, created, b"definitely not a video")
    client.post(f"/analyses/{analysis_id}/start")
    run(settings, once=True)

    summary = client.get(f"/analyses/{analysis_id}").json()
    assert summary["status"] == "failed"
    assert summary["error"]["code"] == "UNREADABLE_VIDEO"
    assert "/" not in summary["error"]["message"]  # no server paths leak

    assert client.post(f"/analyses/{analysis_id}/retry").json()["status"] == "queued"
    assert client.post(f"/analyses/{analysis_id}/retry").status_code == 409


def test_list_is_newest_first_and_paginates(client):
    ids = [create(client)["analysis"]["id"] for _ in range(3)]
    first = client.get("/analyses", params={"limit": 2}).json()
    assert [a["id"] for a in first["items"]] == ids[::-1][:2]
    second = client.get("/analyses", params={"limit": 2, "cursor": first["next_cursor"]}).json()
    assert [a["id"] for a in second["items"]] == [ids[0]]
    assert second["next_cursor"] is None


@pytest.mark.integration
def test_full_flow_on_sample_clip(client, settings):
    body = CLIP.read_bytes()
    created = create(client, size=len(body))
    analysis_id = created["analysis"]["id"]
    upload(client, created, body)
    client.post(f"/analyses/{analysis_id}/start")
    run(settings, once=True)

    summary = client.get(f"/analyses/{analysis_id}").json()
    assert summary["status"] == "succeeded", summary
    assert sum(summary["counts"].values()) > 0
    assert summary["thumbnail_url"]

    result = client.get(f"/analyses/{analysis_id}/result")
    assert result.status_code == 200
    data = schemas.AnalysisResult.model_validate(result.json())
    assert data.phases.contact is not None
    assert data.feedback and data.feedback[0].text

    frames_res = client.get(f"/analyses/{analysis_id}/frames", headers={"Accept-Encoding": "gzip"})
    assert frames_res.headers["content-encoding"] == "gzip"
    assert "immutable" in frames_res.headers["cache-control"]
    frames = schemas.FramesPayload.model_validate(frames_res.json())
    assert frames.n_frames == data.n_frames == len(frames.series.elbow_angle)
    assert len(frames.landmarks.raw.right_wrist.v) == frames.n_frames

    video = client.get(data.video_url, headers={"Range": "bytes=0-99"})
    assert video.status_code == 206 and len(video.content) == 100
    assert video.headers["content-type"] == "video/mp4"

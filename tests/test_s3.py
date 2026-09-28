"""The S3 storage backend, against a local S3-compatible server (moto)."""

import json
import socket
from pathlib import Path

import boto3
import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from moto.server import ThreadedMotoServer

from serve_api import keys
from serve_api.app import create_app
from serve_api.settings import Settings
from serve_api.storage import S3Storage, make_storage
from serve_api.worker import run
from tests.conftest import sign_in

CLIP = Path(__file__).parent / "fixtures" / "sample_serve.mp4"
BUCKET = "serve-analyzer-test"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def s3_endpoint():
    port = _free_port()
    server = ThreadedMotoServer(ip_address="127.0.0.1", port=port, verbose=False)
    server.start()
    yield f"http://127.0.0.1:{port}"
    server.stop()


@pytest.fixture
def settings(tmp_path, s3_endpoint, monkeypatch) -> Settings:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    bucket = f"{BUCKET}-{tmp_path.name.lower().replace('_', '-')}"[:63]
    boto3.client("s3", endpoint_url=s3_endpoint, region_name="us-east-1").create_bucket(Bucket=bucket)
    return Settings(data_dir=tmp_path, secret="test", public_base="", storage="s3",
                    s3_bucket=bucket, s3_region="us-east-1", s3_endpoint_url=s3_endpoint)


def test_s3_storage_round_trip(settings, tmp_path):
    storage = make_storage(settings)
    assert isinstance(storage, S3Storage)
    url, _ = storage.presign("PUT", "uploads/a/input.mp4", "video/mp4")
    assert httpx.put(url, content=b"video bytes", headers={"Content-Type": "video/mp4"}).status_code == 200
    assert storage.size("uploads/a/input.mp4") == 11
    assert storage.size("uploads/missing/input.mp4") is None
    with storage.local_copy("uploads/a/input.mp4") as path:
        assert path.read_bytes() == b"video bytes"

    out = tmp_path / "out"
    out.mkdir()
    (out / "results.json").write_text('{"ok": true}')
    (out / "thumbnail.jpg").write_bytes(b"jpg")
    storage.publish(out, "analyses/a")
    assert json.loads(storage.read_bytes("analyses/a/results.json")) == {"ok": True}
    get_url, _ = storage.presign("GET", "analyses/a/thumbnail.jpg")
    res = httpx.get(get_url)
    assert res.content == b"jpg" and res.headers["content-type"] == "image/jpeg"

    storage.delete_prefix("uploads/a")
    assert storage.size("uploads/a/input.mp4") is None


def test_upload_urls_sign_the_content_type(settings):
    """S3 then refuses an upload with any other Content-Type (moto doesn't check signatures,
    so this checks what is signed)."""
    url, expires = make_storage(settings).presign("PUT", "uploads/b/input.mp4", "video/mp4")
    query = dict(httpx.URL(url).params)
    assert query["X-Amz-SignedHeaders"] == "content-type;host"
    assert query["X-Amz-Expires"] == str(settings.upload_url_ttl_s)


def test_oversized_uploads_are_caught_when_the_analysis_starts(settings):
    from dataclasses import replace

    client = sign_in(TestClient(create_app(replace(settings, max_upload_bytes=100))))
    created = client.post("/analyses", json={
        "hand": "right", "filename": "a.mp4", "content_type": "video/mp4", "size_bytes": 50,
    }).json()
    target = created["upload"]
    # S3 accepts whatever size the browser sends, whatever it declared.
    assert httpx.put(target["url"], content=b"x" * 500, headers=target["headers"]).status_code == 200
    res = client.post(f"/analyses/{created['analysis']['id']}/start")
    assert res.status_code == 413
    assert make_storage(settings).size(keys.input_key(created["analysis"]["id"], "video/mp4")) is None


def test_the_local_storage_routes_do_not_exist_with_s3(settings):
    client = TestClient(create_app(settings))
    assert client.get("/storage/uploads/a/input.mp4", params={"expires": 1, "sig": "x"}).status_code == 404


@pytest.mark.integration
def test_full_flow_through_s3(settings):
    client = sign_in(TestClient(create_app(settings)))
    body = CLIP.read_bytes()
    created = client.post("/analyses", json={
        "hand": "right", "filename": "serve.mp4", "content_type": "video/mp4", "size_bytes": len(body),
    }).json()
    target, analysis_id = created["upload"], created["analysis"]["id"]
    assert target["url"].startswith(settings.s3_endpoint_url)
    assert httpx.put(target["url"], content=body, headers=target["headers"]).status_code == 200
    assert client.post(f"/analyses/{analysis_id}/start").status_code == 202

    run(settings, once=True)

    summary = client.get(f"/analyses/{analysis_id}").json()
    assert summary["status"] == "succeeded", summary
    result = client.get(f"/analyses/{analysis_id}/result").json()
    assert result["phases"]["contact"] is not None
    assert client.get(f"/analyses/{analysis_id}/frames").json()["n_frames"] > 0
    video = httpx.get(result["video_url"], headers={"Range": "bytes=0-99"})
    assert video.status_code == 206 and len(video.content) == 100
    assert httpx.get(summary["thumbnail_url"]).headers["content-type"] == "image/jpeg"

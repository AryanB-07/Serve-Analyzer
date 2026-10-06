"""Consent at signup and the retention policy for original uploads."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from serve_api import keys, worker
from serve_api.app import create_app
from serve_api.auth import TERMS_VERSION
from serve_api.db import now
from serve_api.settings import Settings
from serve_api.storage import LocalStorage
from serve_api.tables import analyses, users
from tests.conftest import FakeMailer, sign_in

PASSWORD = "correct horse battery"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path, secret="test", public_base="")


@pytest.fixture
def app(settings):
    return create_app(settings, FakeMailer())


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


@pytest.mark.parametrize("body", [{}, {"accept_terms": False}])
def test_signup_needs_the_terms_accepted(client, body):
    res = client.post("/auth/signup", json={"email": "a@example.com", "password": PASSWORD, **body})
    assert res.status_code == 422
    if body:
        assert "accept the Terms of Service and Privacy Policy" in res.text


def test_signup_records_which_terms_were_accepted_and_when(app, client):
    before = now()
    sign_in(client, "a@example.com")
    with app.state.auth.db.engine.connect() as conn:
        row = conn.execute(select(users.c.terms_version, users.c.terms_accepted_at)).one()
    assert row.terms_version == TERMS_VERSION
    assert before <= row.terms_accepted_at <= now()


def _analysis(app, settings, client, status: str, age_days: float) -> str:
    """An analysis of the given status and age, with its original upload and results stored."""
    db, storage = app.state.auth.db, LocalStorage(settings)
    analysis_id = client.post("/analyses", json={"hand": "right", "filename": "a.mp4",
                                                 "content_type": "video/mp4", "size_bytes": 1}).json()["analysis"]["id"]
    for key in (keys.input_key(analysis_id, "video/mp4"), keys.output_key(analysis_id, keys.PLAYBACK)):
        storage.path(key).parent.mkdir(parents=True, exist_ok=True)
        storage.path(key).write_bytes(b"x")
    with db.engine.begin() as conn:
        conn.execute(update(analyses).where(analyses.c.id == analysis_id).values(
            status=status, created_at=now() - timedelta(days=age_days)))
    return analysis_id


def test_original_uploads_are_deleted_after_the_retention_period(app, client, settings):
    sign_in(client)
    old_done = _analysis(app, settings, client, "succeeded", 31)
    old_failed = _analysis(app, settings, client, "failed", 40)
    recent = _analysis(app, settings, client, "succeeded", 29)
    still_queued = _analysis(app, settings, client, "queued", 45)
    db, storage = app.state.auth.db, LocalStorage(settings)

    worker.housekeeping(db, storage, upload_retention_days=30)

    def has_input(i):
        return storage.size(keys.input_key(i, "video/mp4")) is not None

    assert not has_input(old_done) and not has_input(old_failed)
    assert has_input(recent) and has_input(still_queued)
    # The results (with their own playback copy) stay until the person deletes them.
    assert storage.size(keys.output_key(old_done, keys.PLAYBACK)) == 1
    assert db.get(old_done)["input_deleted_at"] is not None
    assert db.get(recent)["input_deleted_at"] is None
    assert db.expire_inputs(now() - timedelta(days=30)) == []  # nothing is redone next hour


def test_retention_can_be_turned_off(app, client, settings):
    sign_in(client)
    old = _analysis(app, settings, client, "succeeded", 400)
    worker.housekeeping(app.state.auth.db, LocalStorage(settings), upload_retention_days=0)
    assert LocalStorage(settings).size(keys.input_key(old, "video/mp4")) == 1


def test_a_failed_analysis_without_its_original_cannot_be_retried(app, client, settings):
    sign_in(client)
    old_failed = _analysis(app, settings, client, "failed", 40)
    worker.housekeeping(app.state.auth.db, LocalStorage(settings), upload_retention_days=30)
    res = client.post(f"/analyses/{old_failed}/retry")
    assert res.status_code == 409
    assert res.json()["detail"] == ("Original videos are kept for 30 days, so this analysis can't be "
                                    "retried. Upload the video again instead.")


def test_a_failed_analysis_with_its_original_can_still_be_retried(app, client, settings):
    sign_in(client)
    recent_failed = _analysis(app, settings, client, "failed", 1)
    assert client.post(f"/analyses/{recent_failed}/retry").status_code == 202

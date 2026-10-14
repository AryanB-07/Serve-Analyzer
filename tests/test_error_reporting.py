"""Optional exception reporting: off without a DSN, and nothing private in what it sends."""

import logging

import pytest
import sentry_sdk
from fastapi.testclient import TestClient
from sentry_sdk.transport import Transport

from serve_api.app import create_app
from serve_api.error_reporting import init_error_reporting, scrub_event, scrub_text
from serve_api.settings import Settings
from tests.conftest import sign_in

DSN = "https://public@errors.example.com/1"


class Captured(Transport):
    """Keeps events instead of sending them."""

    events: list[dict] = []

    def capture_envelope(self, envelope) -> None:
        for item in envelope.items:
            if item.type == "event":
                Captured.events.append(item.payload.json)


@pytest.fixture
def reporting(monkeypatch):
    Captured.events = []
    real_init = sentry_sdk.init
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: real_init(transport=Captured, **kw))
    yield Captured.events
    real_init()  # an inactive client: nothing reported by later tests
    monkeypatch.undo()


def test_nothing_is_set_up_or_sent_without_a_dsn(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: calls.append(kw))
    assert init_error_reporting(Settings(data_dir=tmp_path), "api") is False
    create_app(Settings(data_dir=tmp_path, secret="test"))
    assert calls == []


def test_it_reports_errors_only_without_tracing_or_personal_data(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: seen.update(kw))
    monkeypatch.setattr(sentry_sdk, "set_tag", lambda *a: None)
    assert init_error_reporting(Settings(data_dir=tmp_path, sentry_dsn=DSN), "worker") is True
    assert seen["dsn"] == DSN
    assert seen["traces_sample_rate"] == 0.0  # no performance events eating the free quota
    assert not seen.get("send_default_pii")
    assert seen["include_local_variables"] is False
    assert seen["include_source_context"] is False
    assert seen["max_request_body_size"] == "never"
    assert seen["before_send"] is scrub_event


def test_an_unhandled_api_error_is_reported_without_the_request_details(tmp_path, reporting):
    app = create_app(Settings(data_dir=tmp_path, secret="test", public_base="", sentry_dsn=DSN))

    @app.get("/explode")
    def explode():
        raise RuntimeError("could not process alice@example.com with token " + "x" * 40)

    client = sign_in(TestClient(app, raise_server_exceptions=False), "alice@example.com")
    assert client.get("/explode?token=secret-link-token").status_code == 500
    sentry_sdk.flush()
    assert len(reporting) == 1
    event = reporting[0]
    text = str(event)
    assert "RuntimeError" in text
    assert event["request"] == {"method": "GET", "url": "http://testserver/explode"}
    for private in ("alice@example.com", "secret-link-token", "serve_session", "x" * 40):
        assert private not in text
    assert "user" not in event
    frames = event["exception"]["values"][0]["stacktrace"]["frames"]
    assert all("vars" not in f and "context_line" not in f for f in frames)


def test_logged_errors_are_reported_but_ordinary_logs_are_not(tmp_path, reporting):
    init_error_reporting(Settings(data_dir=tmp_path, sentry_dsn=DSN), "worker")
    worker_log = logging.getLogger("serve_api.worker")
    worker_log.info("analysis a1 failed: NOT_A_SERVE (a user's video, not a bug)")
    worker_log.warning("requeued 1 analyses whose worker stopped responding")
    try:
        raise ValueError("boom")
    except ValueError:
        worker_log.exception("could not send 'Reset' to bob@example.com")
    sentry_sdk.flush()
    assert len(reporting) == 1
    assert "bob@example.com" not in str(reporting[0])
    assert "[email]" in str(reporting[0])


@pytest.mark.parametrize("text, expected", [
    ("mail to a.b+c@sub.example.co.uk failed", "mail to [email] failed"),
    ("token=" + "A1b2_" * 10, "token=[token]"),
    ("analysis 4f1c2a3b failed", "analysis 4f1c2a3b failed"),  # short ids stay, for debugging
])
def test_text_is_masked(text, expected):
    assert scrub_text(text) == expected

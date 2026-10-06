"""Email verification, password reset, and deleting analyses and accounts."""

import smtplib
import uuid
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from serve_api import keys, worker
from serve_api.app import create_app
from serve_api.db import now
from serve_api.mailer import Email, OutboxMailer, SmtpMailer
from serve_api.purge import run_purges
from serve_api.settings import Settings
from serve_api.storage import LocalStorage
from serve_api.tables import email_tokens, sessions, storage_purges, users
from tests.conftest import FakeMailer
from tests.test_queue import fake_analyze

PASSWORD = "correct horse battery"
NEW_PASSWORD = "a brand new passphrase"


@pytest.fixture
def mailer() -> FakeMailer:
    return FakeMailer()


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path, secret="test", public_base="", verify_email=True,
                    app_url="https://serve.example.com")


@pytest.fixture
def app(settings, mailer):
    return create_app(settings, mailer)


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


def db_of(app):
    return app.state.auth.db


def signup(client: TestClient, email: str | None = None) -> str:
    email = email or f"{uuid.uuid4().hex[:10]}@example.com"
    res = client.post("/auth/signup", json={"email": email, "password": PASSWORD, "accept_terms": True})
    assert res.status_code == 201, res.text
    return email


def token_from(link: str) -> str:
    return parse_qs(urlsplit(link).query)["token"][0]


def create_analysis(client: TestClient):
    return client.post("/analyses", json={"hand": "right", "filename": "serve.mp4",
                                          "content_type": "video/mp4", "size_bytes": 10})


def verify(client: TestClient, mailer: FakeMailer, email: str) -> None:
    res = client.post("/auth/verify-email", json={"token": token_from(mailer.last_link(email))})
    assert res.status_code == 204


def uploaded_analysis(client: TestClient, settings: Settings) -> str:
    """An analysis whose video is in storage and whose results have been published."""
    analysis_id = create_analysis(client).json()["analysis"]["id"]
    storage = LocalStorage(settings)
    for key in (keys.input_key(analysis_id, "video/mp4"), keys.output_key(analysis_id, keys.RESULTS)):
        storage.path(key).parent.mkdir(parents=True, exist_ok=True)
        storage.path(key).write_bytes(b"x")
    return analysis_id


# --- email verification ----------------------------------------------------------------

def test_signup_emails_a_link_that_verifies_the_address(client, mailer):
    email = signup(client)
    assert client.get("/auth/me").json()["email_verified"] is False
    link = mailer.last_link(email)
    assert link.startswith("https://serve.example.com/verify-email?token=")
    assert mailer.sent[-1].subject == "Confirm your email for Serve Analyzer"
    verify(client, mailer, email)
    assert client.get("/auth/me").json()["email_verified"] is True


def test_a_verification_link_works_once_and_without_signing_in(app, client, mailer):
    email = signup(client)
    token = token_from(mailer.last_link(email))
    other_device = TestClient(app)
    assert other_device.post("/auth/verify-email", json={"token": token}).status_code == 204
    again = other_device.post("/auth/verify-email", json={"token": token})
    assert again.status_code == 400 and "invalid or has expired" in again.json()["detail"]


def test_an_expired_or_superseded_link_is_refused(app, client, mailer):
    email = signup(client)
    first = token_from(mailer.last_link(email))
    assert client.post("/auth/verify-email/resend").status_code == 202
    second = token_from(mailer.last_link(email))
    assert client.post("/auth/verify-email", json={"token": first}).status_code == 400
    with db_of(app).engine.begin() as conn:
        conn.execute(update(email_tokens).values(expires_at=now() - timedelta(days=2)))
    assert client.post("/auth/verify-email", json={"token": second}).status_code == 400


def test_the_database_stores_only_token_hashes(app, client, mailer):
    email = signup(client)
    token = token_from(mailer.last_link(email))
    with db_of(app).engine.connect() as conn:
        stored = conn.execute(select(email_tokens.c.token_hash)).scalars().all()
    assert token not in stored and len(stored) == 1


def test_analysing_needs_a_verified_email_when_required(client, mailer):
    email = signup(client)
    refused = create_analysis(client)
    assert refused.status_code == 403 and "Confirm your email" in refused.json()["detail"]
    verify(client, mailer, email)
    assert create_analysis(client).status_code == 201


def test_development_does_not_require_verification_by_default(tmp_path, mailer):
    client = TestClient(create_app(Settings(data_dir=tmp_path, secret="t", public_base=""), mailer))
    signup(client)
    assert create_analysis(client).status_code == 201


def test_resending_is_limited_and_skipped_once_verified(client, mailer):
    email = signup(client)  # the signup email counts towards the limit
    assert client.post("/auth/verify-email/resend").status_code == 202
    assert client.post("/auth/verify-email/resend").status_code == 202
    limited = client.post("/auth/verify-email/resend")
    assert limited.status_code == 429 and "Retry-After" in limited.headers
    assert len(mailer.sent) == 3
    verify(client, mailer, email)
    assert client.post("/auth/verify-email/resend").status_code == 202
    assert len(mailer.sent) == 3


# --- password reset --------------------------------------------------------------------

def test_reset_gives_the_same_answer_for_unknown_addresses(client, mailer):
    res = client.post("/auth/password-reset", json={"email": "nobody@example.com"})
    assert res.status_code == 202 and mailer.sent == []


def test_reset_sets_a_new_password_and_signs_out_everywhere(app, client, mailer):
    email = signup(client)
    other_device = TestClient(app)
    assert other_device.post("/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
    assert client.post("/auth/password-reset", json={"email": email.upper()}).status_code == 202
    link = mailer.last_link(email)
    assert link.startswith("https://serve.example.com/reset-password?token=")
    res = client.post("/auth/password-reset/confirm",
                      json={"token": token_from(link), "password": NEW_PASSWORD})
    assert res.status_code == 204
    assert other_device.get("/auth/me").status_code == 401
    assert client.get("/auth/me").status_code == 401
    with db_of(app).engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(sessions)).scalar_one() == 0
    assert client.post("/auth/login", json={"email": email, "password": PASSWORD}).status_code == 401
    me = client.post("/auth/login", json={"email": email, "password": NEW_PASSWORD})
    assert me.status_code == 200
    assert me.json()["email_verified"] is True  # following the link proved the inbox is theirs
    assert mailer.sent[-1].subject == "Your Serve Analyzer password was changed"


def test_a_reset_link_works_once(client, mailer):
    email = signup(client)
    client.post("/auth/password-reset", json={"email": email})
    token = token_from(mailer.last_link(email))
    body = {"token": token, "password": NEW_PASSWORD}
    assert client.post("/auth/password-reset/confirm", json=body).status_code == 204
    assert client.post("/auth/password-reset/confirm", json=body).status_code == 400


def test_a_verification_link_cannot_reset_a_password(client, mailer):
    email = signup(client)
    token = token_from(mailer.last_link(email))
    res = client.post("/auth/password-reset/confirm", json={"token": token, "password": NEW_PASSWORD})
    assert res.status_code == 400


def test_reset_emails_are_limited_without_saying_so(client, mailer):
    email = signup(client)
    for _ in range(4):
        assert client.post("/auth/password-reset", json={"email": email}).status_code == 202
    assert len(mailer.sent) == 3  # signup + two resets; the rest are silently skipped


def test_a_new_password_must_be_long_enough(client, mailer):
    email = signup(client)
    client.post("/auth/password-reset", json={"email": email})
    res = client.post("/auth/password-reset/confirm",
                      json={"token": token_from(mailer.last_link(email)), "password": "short"})
    assert res.status_code == 422


# --- deleting an analysis --------------------------------------------------------------

def test_deleting_an_analysis_removes_its_video_and_results(client, mailer, settings):
    verify(client, mailer, signup(client))
    analysis_id = uploaded_analysis(client, settings)
    storage = LocalStorage(settings)
    assert client.delete(f"/analyses/{analysis_id}").status_code == 204
    assert client.get(f"/analyses/{analysis_id}").status_code == 404
    assert storage.size(keys.input_key(analysis_id, "video/mp4")) is None
    assert storage.size(keys.output_key(analysis_id, keys.RESULTS)) is None
    assert client.delete(f"/analyses/{analysis_id}").status_code == 404


def test_nobody_else_can_delete_your_analysis(app, client, mailer, settings):
    verify(client, mailer, signup(client))
    analysis_id = uploaded_analysis(client, settings)
    stranger = TestClient(app)
    signup(stranger)
    assert stranger.delete(f"/analyses/{analysis_id}").status_code == 404
    assert client.get(f"/analyses/{analysis_id}").status_code == 200


def test_a_failed_file_deletion_is_retried_by_housekeeping(app, client, mailer, settings, monkeypatch):
    verify(client, mailer, signup(client))
    analysis_id = uploaded_analysis(client, settings)

    def broken(prefix):
        raise OSError("storage unavailable")

    monkeypatch.setattr(LocalStorage, "delete_prefix", lambda self, prefix: broken(prefix))
    assert client.delete(f"/analyses/{analysis_id}").status_code == 204  # the row is gone regardless
    db = db_of(app)
    assert len(db.pending_purges()) == 2
    monkeypatch.undo()
    storage = LocalStorage(settings)
    worker.housekeeping(db, storage)
    assert db.pending_purges() == []
    assert storage.size(keys.input_key(analysis_id, "video/mp4")) is None


def test_an_analysis_deleted_while_processing_leaves_no_files(app, client, mailer, settings, monkeypatch):
    verify(client, mailer, signup(client))
    analysis_id = uploaded_analysis(client, settings)
    db, storage = db_of(app), LocalStorage(settings)
    assert db.transition(analysis_id, ("awaiting_upload",), "queued")
    job = db.claim_next("worker-a")
    monkeypatch.setattr(worker, "analyze", fake_analyze(0.01))
    real_publish = storage.publish

    def publish_then_deleted(local_dir, prefix):
        real_publish(local_dir, prefix)
        assert client.delete(f"/analyses/{analysis_id}").status_code == 204

    monkeypatch.setattr(storage, "publish", publish_then_deleted)
    worker.process(job, db, storage, "worker-a")
    assert db.get(analysis_id) is None
    assert storage.size(keys.output_key(analysis_id, keys.RESULTS)) is None


# --- deleting an account ---------------------------------------------------------------

def test_deleting_an_account_needs_the_password(client, mailer):
    signup(client)
    res = client.request("DELETE", "/auth/me", json={"password": "wrong password"})
    assert res.status_code == 403 and res.json()["detail"] == "Incorrect password."
    assert client.get("/auth/me").status_code == 200


def test_deleting_an_account_removes_everything_it_owns(app, client, mailer, settings):
    email = signup(client)
    verify(client, mailer, email)
    mine = [uploaded_analysis(client, settings) for _ in range(2)]
    other = TestClient(app)
    other_email = signup(other)
    verify(other, mailer, other_email)
    theirs = uploaded_analysis(other, settings)

    res = client.request("DELETE", "/auth/me", json={"password": PASSWORD})
    assert res.status_code == 204
    assert 'serve_session=""' in res.headers["set-cookie"] or "Max-Age=0" in res.headers["set-cookie"]
    assert client.get("/auth/me").status_code == 401
    assert client.post("/auth/login", json={"email": email, "password": PASSWORD}).status_code == 401
    storage = LocalStorage(settings)
    for analysis_id in mine:
        assert storage.size(keys.input_key(analysis_id, "video/mp4")) is None
        assert storage.size(keys.output_key(analysis_id, keys.RESULTS)) is None
    db = db_of(app)
    with db.engine.connect() as conn:
        assert conn.execute(select(users.c.email)).scalars().all() == [other_email]
        assert conn.execute(select(func.count()).select_from(storage_purges)).scalar_one() == 0
    assert other.get(f"/analyses/{theirs}").status_code == 200
    assert storage.size(keys.input_key(theirs, "video/mp4")) == 1
    assert mailer.sent[-1].to == email and "deleted" in mailer.sent[-1].subject
    # The address is free to sign up again.
    assert client.post("/auth/signup", json={"email": email, "password": PASSWORD, "accept_terms": True}).status_code == 201


def test_wrong_passwords_when_deleting_are_rate_limited(client):
    signup(client)
    for _ in range(10):
        client.request("DELETE", "/auth/me", json={"password": "nope"})
    assert client.request("DELETE", "/auth/me", json={"password": PASSWORD}).status_code == 429


def test_housekeeping_drops_expired_links(app, client, mailer):
    signup(client)
    db = db_of(app)
    with db.engine.begin() as conn:
        conn.execute(update(email_tokens).values(expires_at=now() - timedelta(days=2)))
    db.delete_expired(attempts_before=now())
    with db.engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(email_tokens)).scalar_one() == 0


def test_run_purges_reports_what_is_left(app, settings, monkeypatch):
    db = db_of(app)
    with db.engine.begin() as conn:
        db._queue_purges(conn, ["uploads/a", "analyses/a"])
    monkeypatch.setattr(LocalStorage, "delete_prefix", lambda self, p: (_ for _ in ()).throw(OSError()))
    assert run_purges(db, LocalStorage(settings)) == 2


# --- sending ---------------------------------------------------------------------------

MESSAGE = Email(to="player@example.com", subject="Hello", text="Plain body https://x.test/a",
                html="<p>HTML body</p>")


def test_the_outbox_writes_messages_for_development(tmp_path):
    OutboxMailer(tmp_path / "outbox").send(MESSAGE)
    (eml,) = (tmp_path / "outbox").glob("*.eml")
    raw = eml.read_text()
    assert "To: player@example.com" in raw and "Subject: Hello" in raw and "Plain body" in raw


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.calls = host, port, []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.calls.append("quit")

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, msg):
        self.calls.append(("send", msg["From"], msg["To"], msg["Subject"]))


def test_smtp_uses_starttls_and_logs_in_like_gmail_expects(tmp_path, monkeypatch):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    settings = Settings(data_dir=tmp_path, smtp_host="smtp.gmail.com", smtp_port=587,
                        smtp_username="me@gmail.com", smtp_password="app-password")
    SmtpMailer(settings).send(MESSAGE)
    (server,) = FakeSMTP.instances
    assert (server.host, server.port) == ("smtp.gmail.com", 587)
    assert server.calls == ["starttls", ("login", "me@gmail.com", "app-password"),
                            ("send", "Serve Analyzer <me@gmail.com>", "player@example.com", "Hello"), "quit"]


def test_port_465_uses_implicit_tls(tmp_path, monkeypatch):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    settings = Settings(data_dir=tmp_path, smtp_host="smtp.gmail.com", smtp_port=465,
                        smtp_username="me@gmail.com", smtp_password="pw")
    SmtpMailer(settings).send(MESSAGE)
    assert "starttls" not in FakeSMTP.instances[0].calls


def test_a_failed_send_does_not_break_signup(tmp_path):
    class Broken:
        def send(self, message):
            raise smtplib.SMTPException("down")

    client = TestClient(create_app(Settings(data_dir=tmp_path, secret="t", public_base=""), Broken()))
    assert client.post("/auth/signup", json={"email": "a@example.com", "password": PASSWORD, "accept_terms": True}).status_code == 201

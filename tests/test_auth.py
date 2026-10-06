"""Accounts, sessions, rate limits and the cross-origin guard."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from serve_api.app import create_app
from serve_api.auth import SESSION_COOKIE, RateLimiter, hash_token
from serve_api.db import now
from serve_api.settings import Settings
from serve_api.tables import auth_attempts, sessions, users
from tests.conftest import FakeMailer, production_settings

PASSWORD = "correct horse battery"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path, secret="test", public_base="")


@pytest.fixture
def client(settings) -> TestClient:
    return TestClient(create_app(settings))


def db(client: TestClient):
    return client.app.state.auth.db


def signup(client: TestClient, email: str = "Player@Example.com", password: str = PASSWORD):
    return client.post("/auth/signup", json={"email": email, "password": password})


def login(client: TestClient, email: str = "player@example.com", password: str = PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_signup_signs_in_with_a_hardened_cookie(client):
    res = signup(client)
    assert res.status_code == 201
    assert res.json()["email"] == "player@example.com"
    cookie = res.headers["set-cookie"].lower()
    assert f"{SESSION_COOKIE}=" in cookie
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
    assert "secure" not in cookie  # development default: plain http on localhost
    assert client.get("/auth/me").json()["email"] == "player@example.com"


def test_emails_are_unique_regardless_of_case(client):
    assert signup(client, "a@example.com").status_code == 201
    dup = signup(TestClient(client.app), "A@EXAMPLE.com")
    assert dup.status_code == 409
    assert "already exists" in dup.json()["detail"]


def test_signup_validates_email_and_password_length(client):
    assert signup(client, email="not-an-email").status_code == 422
    assert signup(client, password="short").status_code == 422
    assert signup(client, password="x" * 257).status_code == 422


def test_wrong_password_and_unknown_email_get_the_same_answer(client):
    signup(client)
    fresh = TestClient(client.app)
    wrong = login(fresh, password="wrong password")
    unknown = login(fresh, email="nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Incorrect email or password."}
    assert SESSION_COOKIE not in fresh.cookies


def test_login_is_case_insensitive_and_me_needs_a_session(client):
    signup(client)
    fresh = TestClient(client.app)
    assert fresh.get("/auth/me").status_code == 401
    assert login(fresh, email="PLAYER@example.COM").status_code == 200
    assert fresh.get("/auth/me").status_code == 200


def test_logout_revokes_the_session_on_the_server(client):
    signup(client)
    token = client.cookies[SESSION_COOKIE]
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401
    replay = TestClient(client.app, cookies={SESSION_COOKIE: token})
    assert replay.get("/auth/me").status_code == 401
    assert TestClient(client.app).post("/auth/logout").status_code == 204  # idempotent


def test_logging_in_again_replaces_the_previous_session(client):
    signup(client)
    old = client.cookies[SESSION_COOKIE]
    login(client)
    new = client.cookies[SESSION_COOKIE]
    assert new != old
    assert TestClient(client.app, cookies={SESSION_COOKIE: old}).get("/auth/me").status_code == 401
    assert TestClient(client.app, cookies={SESSION_COOKIE: new}).get("/auth/me").status_code == 200


def test_only_hashes_are_stored(client):
    signup(client)
    token = client.cookies[SESSION_COOKIE]
    with db(client).engine.connect() as conn:
        user = conn.execute(select(users)).mappings().one()
        session = conn.execute(select(sessions)).mappings().one()
    assert user["password_hash"].startswith("$argon2id$") and PASSWORD not in user["password_hash"]
    assert session["token_hash"] == hash_token(token) != token


def test_expired_sessions_are_refused(client):
    signup(client)
    with db(client).engine.begin() as conn:
        conn.execute(update(sessions).values(expires_at=now() - timedelta(seconds=1)))
    assert client.get("/auth/me").status_code == 401


def test_active_sessions_slide_forward_at_most_daily(client):
    signup(client)
    with db(client).engine.begin() as conn:
        conn.execute(update(sessions).values(last_seen_at=now() - timedelta(hours=2)))
    quiet = client.get("/auth/me")
    assert "set-cookie" not in quiet.headers  # under a day: no write, no new cookie
    stale = now() - timedelta(days=2)
    with db(client).engine.begin() as conn:
        conn.execute(update(sessions).values(last_seen_at=stale, expires_at=now() + timedelta(days=28)))
    res = client.get("/auth/me")
    assert res.status_code == 200 and SESSION_COOKIE in res.headers["set-cookie"]
    with db(client).engine.connect() as conn:
        row = conn.execute(select(sessions)).mappings().one()
    assert row["expires_at"] > now() + timedelta(days=29)
    assert row["last_seen_at"] > stale


def test_repeated_failures_lock_the_email_for_a_while(client):
    signup(client)
    fresh = TestClient(client.app)
    for _ in range(10):
        assert login(fresh, password="wrong password").status_code == 401
    blocked = login(fresh)  # even the right password, until the window passes
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
    assert login(fresh, email="other@example.com").status_code == 401  # other emails unaffected


def test_each_ip_is_limited_across_signup_and_login(client):
    for i in range(30):
        assert signup(TestClient(client.app), email=f"u{i}@example.com").status_code == 201
    assert signup(client, email="one-more@example.com").status_code == 429
    assert login(client, email="u0@example.com").status_code == 429


def test_rate_limits_are_shared_through_the_database(client):
    database = db(client)
    limiter = RateLimiter(database, "test", limit=2, window=timedelta(minutes=1))
    limiter.hit("k")
    limiter.hit("k")
    assert 55 < limiter.retry_after("k") <= 60
    assert limiter.retry_after("other") is None
    # A second API process (another limiter on the same database) sees the same count.
    assert RateLimiter(database, "test", limit=2, window=timedelta(minutes=1)).retry_after("k")
    assert RateLimiter(database, "another-scope", limit=2, window=timedelta(minutes=1)).retry_after("k") is None
    with database.engine.begin() as conn:  # a minute later the window has moved on
        conn.execute(update(auth_attempts).values(at=now() - timedelta(minutes=1, seconds=1)))
    assert limiter.retry_after("k") is None


def test_rate_limit_rows_do_not_store_emails(client):
    signup(client)
    login(TestClient(client.app), password="wrong password")
    with db(client).engine.connect() as conn:
        stored = [r.key_hash for r in conn.execute(select(auth_attempts))]
    assert stored and all(len(h) == 64 and "@" not in h for h in stored)


def test_cross_origin_writes_are_refused(settings):
    client = TestClient(create_app(settings))
    foreign = {"origin": "https://evil.example"}
    assert client.post("/auth/signup", json={"email": "a@example.com", "password": PASSWORD},
                       headers=foreign).status_code == 403
    assert client.post("/auth/logout", headers=foreign).status_code == 403
    assert client.get("/auth/me", headers=foreign).status_code == 401  # reads aren't blocked
    same = {"origin": "http://testserver"}
    assert client.post("/auth/signup", json={"email": "a@example.com", "password": PASSWORD},
                       headers=same).status_code == 201


def test_extra_origins_can_be_allowed(tmp_path):
    settings = Settings(data_dir=tmp_path, secret="t", public_base="",
                        allowed_origins=("https://app.example",))
    client = TestClient(create_app(settings))
    res = client.post("/auth/logout", headers={"origin": "https://app.example"})
    assert res.status_code == 204


def test_cookies_are_secure_outside_development(tmp_path):
    settings = production_settings(tmp_path, public_base="")
    res = signup(TestClient(create_app(settings, FakeMailer()), base_url="https://testserver"))
    assert res.status_code == 201
    assert "secure" in res.headers["set-cookie"].lower()

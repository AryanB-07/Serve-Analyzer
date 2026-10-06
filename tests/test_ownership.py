"""Users only ever see and act on their own analyses."""

from datetime import UTC, datetime

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from serve_api import keys, migrate
from serve_api.app import create_app
from serve_api.auth import verify_password
from serve_api.db import Database
from serve_api.migrate import alembic_config
from serve_api.settings import Settings
from serve_api.storage import LocalStorage
from serve_api.tables import analyses, users
from tests.conftest import sign_in

ANALYSIS_ROUTES = [
    ("get", "/analyses/{id}"),
    ("post", "/analyses/{id}/start"),
    ("post", "/analyses/{id}/retry"),
    ("get", "/analyses/{id}/result"),
    ("get", "/analyses/{id}/frames"),
]


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path, secret="test", public_base="")


@pytest.fixture
def app(settings):
    return create_app(settings)


def create(client: TestClient) -> dict:
    res = client.post("/analyses", json={
        "hand": "right", "filename": "serve.mp4", "content_type": "video/mp4", "size_bytes": 10,
    })
    assert res.status_code == 201, res.text
    return res.json()


def succeed(settings: Settings, app, analysis_id: str) -> None:
    """Pretend the worker finished, so result and frames are readable."""
    storage = LocalStorage(settings)
    for name, body in ((keys.RESULTS, "{}"), (keys.FRAMES, "{}")):
        path = storage.path(keys.output_key(analysis_id, name))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    app.state.auth.db.set_status(analysis_id, "succeeded")


def test_signed_out_requests_are_refused_everywhere(app):
    anon = TestClient(app)
    owner = sign_in(TestClient(app))
    analysis_id = create(owner)["analysis"]["id"]
    assert anon.get("/analyses").status_code == 401
    assert anon.post("/analyses", json={"hand": "right", "filename": "a.mp4",
                                        "content_type": "video/mp4", "size_bytes": 1}).status_code == 401
    for method, route in ANALYSIS_ROUTES:
        assert getattr(anon, method)(route.format(id=analysis_id)).status_code == 401, route


def test_another_users_analysis_does_not_exist_for_you(app, settings):
    alice, bob = sign_in(TestClient(app)), sign_in(TestClient(app))
    analysis_id = create(alice)["analysis"]["id"]
    succeed(settings, app, analysis_id)
    for method, route in ANALYSIS_ROUTES:
        url = route.format(id=analysis_id)
        res = getattr(bob, method)(url)
        assert res.status_code == 404, (route, res.status_code)
        assert res.json() == {"detail": "Analysis not found"}  # same as a made-up id
    assert bob.get("/analyses/not-a-real-id").json() == {"detail": "Analysis not found"}
    assert alice.get(f"/analyses/{analysis_id}/frames").status_code == 200  # the owner still can


def test_bob_cannot_start_or_retry_alices_analysis(app):
    alice, bob = sign_in(TestClient(app)), sign_in(TestClient(app))
    created = create(alice)
    target, analysis_id = created["upload"], created["analysis"]["id"]
    assert alice.put(target["url"], content=b"video", headers=target["headers"]).status_code == 204
    assert bob.post(f"/analyses/{analysis_id}/start").status_code == 404
    assert alice.get(f"/analyses/{analysis_id}").json()["status"] == "awaiting_upload"
    app.state.auth.db.set_status(analysis_id, "failed", error_code="INTERNAL", error_message="x")
    assert bob.post(f"/analyses/{analysis_id}/retry").status_code == 404
    assert alice.get(f"/analyses/{analysis_id}").json()["status"] == "failed"


def test_history_lists_only_your_own_analyses(app):
    alice, bob = sign_in(TestClient(app)), sign_in(TestClient(app))
    mine = [create(alice)["analysis"]["id"] for _ in range(3)]
    theirs = create(bob)["analysis"]["id"]
    first = alice.get("/analyses", params={"limit": 2}).json()
    second = alice.get("/analyses", params={"limit": 2, "cursor": first["next_cursor"]}).json()
    seen = [i["id"] for i in first["items"] + second["items"]]
    assert seen == mine[::-1] and second["next_cursor"] is None
    assert [i["id"] for i in bob.get("/analyses").json()["items"]] == [theirs]
    # A cursor is only a position: Alice's cursor on Bob's list still shows only Bob's rows.
    with_her_cursor = bob.get("/analyses", params={"cursor": first["next_cursor"]}).json()
    assert {i["id"] for i in with_her_cursor["items"]} <= {theirs}


def test_new_analyses_record_their_owner(app):
    alice = sign_in(TestClient(app), "alice@example.com")
    analysis_id = create(alice)["analysis"]["id"]
    db = app.state.auth.db
    with db.engine.connect() as conn:
        owner = conn.execute(
            select(users.c.email).join(analyses, analyses.c.user_id == users.c.id)
            .where(analyses.c.id == analysis_id)
        ).scalar_one()
    assert owner == "alice@example.com"


def _database_at_0002(tmp_path) -> Database:
    db = Database(Settings(data_dir=tmp_path).sqlalchemy_url)
    cfg = alembic_config(db.engine.url.render_as_string(hide_password=False))
    with db.engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0002")
    return db


def _insert_old_analysis(db: Database, analysis_id: str) -> None:
    ts = datetime.now(UTC).replace(tzinfo=None) if db.engine.dialect.name == "sqlite" \
        else datetime.now(UTC)
    with db.engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO analyses (id, hand, filename, content_type, size_bytes, status,"
            " created_at, updated_at) VALUES (:id, 'right', 'a.mp4', 'video/mp4', 1, 'succeeded',"
            " :ts, :ts)"), {"id": analysis_id, "ts": ts})


def _insert_old_user(db: Database, user_id: str, email: str, ts: datetime) -> None:
    """A user row with only the columns revision 0002 has."""
    if db.engine.dialect.name == "sqlite":
        ts = ts.replace(tzinfo=None)
    with db.engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id, email, password_hash, created_at)"
                          " VALUES (:id, :email, '!', :ts)"), {"id": user_id, "email": email, "ts": ts})


def test_existing_analyses_go_to_the_oldest_account(tmp_path):
    db = _database_at_0002(tmp_path)
    _insert_old_user(db, "first", "first@example.com", datetime(2026, 1, 1, tzinfo=UTC))
    _insert_old_user(db, "second", "second@example.com", datetime(2026, 2, 1, tzinfo=UTC))
    _insert_old_analysis(db, "old1")
    migrate.upgrade(db.engine)
    assert db.get("old1")["user_id"] == "first"


def test_existing_analyses_without_any_account_get_a_placeholder_owner(tmp_path):
    db = _database_at_0002(tmp_path)
    _insert_old_analysis(db, "old1")
    migrate.upgrade(db.engine)
    owner = db.get("old1")["user_id"]
    with db.engine.connect() as conn:
        placeholder = conn.execute(select(users).where(users.c.id == owner)).mappings().one()
    assert placeholder["email"] == "legacy-owner@serve-analyzer.invalid"
    # Nobody can sign in as the placeholder: its reserved domain fails email validation,
    # and its password hash matches nothing.
    client = TestClient(create_app(Settings(data_dir=tmp_path, secret="t", public_base="")))
    res = client.post("/auth/login", json={"email": placeholder["email"], "password": "!"})
    assert res.status_code == 422
    assert not verify_password(placeholder["password_hash"], "!")

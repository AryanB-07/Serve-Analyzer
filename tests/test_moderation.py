"""Notifications, usernames held after they're given up, and suspending accounts."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from serve_api import moderate, worker
from serve_api.db import now
from serve_api.storage import LocalStorage
from serve_api.tables import notifications, released_usernames
from tests.test_account import PASSWORD, app, client, db_of, mailer, signup  # noqa: F401
from tests.test_follows import befriend, person
from tests.test_messages import chat, say
from tests.test_shared_serves import finished, send


@pytest.fixture
def settings(tmp_path):  # no email verification, so analyses can be made straight away
    from serve_api.settings import Settings

    return Settings(data_dir=tmp_path, secret="test", public_base="", verify_email=False)


@pytest.fixture
def ann(app):
    return person(app, "ann")


@pytest.fixture
def bob(app):
    return person(app, "bob")


def kinds(c: TestClient) -> list[tuple[str, str]]:
    return [(n["kind"], n["person"]["username"]) for n in c.get("/notifications").json()]


# --- notifications -------------------------------------------------------------------------------

def test_a_follow_and_a_follow_back_are_announced(app, ann, bob):
    ann.put("/follows/bob")
    assert kinds(bob) == [("new_follower", "ann")]
    assert bob.get("/notifications/unread").json() == {"unread": 1}
    bob.put("/follows/ann")
    assert kinds(ann) == [("followed_back", "bob")]


def test_following_again_doesnt_pile_up_notifications(app, ann, bob):
    for _ in range(3):
        ann.put("/follows/bob")
        ann.delete("/follows/bob")
    ann.put("/follows/bob")
    assert kinds(bob) == [("new_follower", "ann")]


def test_an_unfollow_takes_its_notification_with_it(app, ann, bob):
    ann.put("/follows/bob")
    ann.delete("/follows/bob")
    assert kinds(bob) == []


def test_a_serve_sent_is_announced_with_its_conversation(app, settings, ann, bob):
    befriend(ann, bob, "bob")
    conv = chat(ann, "bob")
    say(ann, conv, "plain text isn't announced: messages have their own badge")
    assert all(k != "serve_received" for k, _ in kinds(bob))
    send(ann, conv, finished(app, settings, ann))
    latest = bob.get("/notifications").json()[0]
    assert latest["kind"] == "serve_received" and latest["conversation_id"] == conv and latest["read"] is False


def test_opening_notifications_marks_them_read(app, ann, bob):
    ann.put("/follows/bob")
    assert bob.post("/notifications/read").status_code == 204
    assert bob.get("/notifications/unread").json() == {"unread": 0}
    assert bob.get("/notifications").json()[0]["read"] is True
    assert TestClient(app).get("/notifications").status_code == 401


def test_notifications_from_blocked_people_go(app, ann, bob):
    befriend(ann, bob, "bob")
    bob.post("/blocks", json={"username": "ann"})
    assert kinds(ann) == [] and kinds(bob) == []


def test_notifications_go_with_the_account_and_after_90_days(app, settings, ann, bob):
    carol = person(app, "carol")
    ann.put("/follows/bob")
    carol.put("/follows/bob")
    ann.request("DELETE", "/auth/me", json={"password": PASSWORD})
    assert kinds(bob) == [("new_follower", "carol")]
    assert bob.get("/auth/me/export").json()["notifications"][0]["username"] == "carol"
    db = db_of(app)
    with db.engine.begin() as conn:
        conn.execute(update(notifications).values(created_at=now() - worker.NOTIFICATIONS_KEPT * 1.01))
    worker.housekeeping(db, LocalStorage(settings))
    assert kinds(bob) == []


# --- usernames given up --------------------------------------------------------------------------

def test_a_released_username_is_held_for_its_owner(app, ann, bob):
    ann.patch("/profile", json={"username": "ann_new"})
    res = bob.patch("/profile", json={"username": "ann"})
    assert res.status_code == 409 and "held" in res.json()["detail"]
    check = bob.get("/profile/username-check", params={"username": "ann"}).json()
    assert check["available"] is False and "held" in check["problem"]
    # Ann can take it back.
    assert ann.get("/profile/username-check", params={"username": "ann"}).json()["available"] is True
    assert ann.patch("/profile", json={"username": "ann"}).status_code == 200
    # ...which holds ann_new for her in turn.
    assert bob.patch("/profile", json={"username": "ann_new"}).status_code == 409


def test_the_hold_ends_after_30_days(app, settings, ann, bob):
    ann.patch("/profile", json={"username": "ann_new"})
    db = db_of(app)
    with db.engine.begin() as conn:
        conn.execute(update(released_usernames).values(released_at=now() - timedelta(days=31)))
    assert bob.patch("/profile", json={"username": "ann"}).status_code == 200
    worker.housekeeping(db, LocalStorage(settings))
    assert db.username_hold("ann") is None


def test_a_deleted_accounts_username_is_held_too(app, ann):
    ann.request("DELETE", "/auth/me", json={"password": PASSWORD})
    newcomer = person(app)
    assert newcomer.patch("/profile", json={"username": "ann"}).status_code == 409


# --- suspension ----------------------------------------------------------------------------------

@pytest.fixture
def ops(app, settings, monkeypatch):
    """Run the moderation script against the test database."""
    monkeypatch.setenv("SERVE_API_DATA_DIR", str(settings.data_dir))
    return lambda *argv: moderate.main(list(argv))


def test_a_suspended_account_cant_sign_in_and_its_sessions_end(app, ann, ops, capsys):
    email = ann.get("/auth/me").json()["email"]
    assert ops("suspend", "@ann", "--reason", "spam") == 0
    assert "Suspended @ann" in capsys.readouterr().out
    assert ann.get("/auth/me").status_code == 401
    res = TestClient(app).post("/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 403 and "suspended" in res.json()["detail"]
    # A wrong password gets the usual answer, so a suspension isn't revealed to a guesser.
    wrong = TestClient(app).post("/auth/login", json={"email": email, "password": "not it"})
    assert wrong.status_code == 401 and "suspended" not in wrong.text


def test_a_suspended_account_disappears_for_everyone_else(app, settings, ann, bob, ops):
    befriend(ann, bob, "bob")
    conv = chat(ann, "bob")
    analysis_id = finished(app, settings, ann)
    send(ann, conv, analysis_id, "my serve")
    for c in (ann, bob):
        c.patch("/profile", json={"on_leaderboard": True})
    carol = person(app, "carol")
    carol.put("/follows/bob")
    ops("suspend", "ann", "--reason", "harassment")
    ops("suspend", "carol", "--reason", "spam")
    assert bob.get("/people/ann").status_code == 404
    assert bob.get("/follows").json()["counts"] == {"followers": 0, "following": 0, "friends": 0}
    assert bob.get("/conversations").json() == [] and bob.get("/conversations/unread").json() == {"unread": 0}
    assert bob.get(f"/analyses/{analysis_id}").status_code == 404
    assert all(e["person"]["username"] != "ann" for e in bob.get("/leaderboard").json()["not_ranked"])
    assert kinds(bob) == []
    # Unsuspending puts it all back.
    ops("unsuspend", "ann")
    assert bob.get("/people/ann").json()["relationship"] == "friends"
    assert bob.get(f"/analyses/{analysis_id}").status_code == 200
    assert len(bob.get("/conversations").json()) == 1


def test_show_lists_the_reports_about_an_account(app, ann, bob, ops, capsys):
    bob.post("/reports", json={"username": "ann", "reason": "harassment", "note": "Mean messages"})
    email = ann.get("/auth/me").json()["email"]
    assert ops("show", email) == 0
    out = capsys.readouterr().out
    assert "status    active" in out and "1 about this account" in out and "Mean messages" in out
    assert ops("show", "nobody_at_all") == 1

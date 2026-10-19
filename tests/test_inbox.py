"""The Received view: serves friends sent you, with who, when and whether you've opened them."""

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, Table, insert, inspect, update

from serve_api import migrate
from serve_api.db import Database, now
from serve_api.settings import Settings
from serve_api.tables import analyses, messages
from tests.test_account import PASSWORD, app, client, db_of, mailer, signup  # noqa: F401
from tests.test_follows import befriend, person
from tests.test_messages import chat
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


@pytest.fixture
def sent(app, settings, ann, bob):
    """Ann, Bob's friend, sends him two serves. Returns (first, second) as (analysis id, message id)."""
    befriend(ann, bob, "bob")
    conv = chat(ann, "bob")
    out = []
    for name in ("first.mp4", "second.mp4"):
        analysis_id = finished(app, settings, ann, filename=name)
        res = send(ann, conv, analysis_id)
        assert res.status_code == 201, res.text
        out.append((analysis_id, res.json()["id"]))
    return out


def inbox(c: TestClient, limit: int = 50) -> list[dict]:
    items, cursor = [], None
    while True:
        res = c.get("/inbox", params={"limit": limit, **({"cursor": cursor} if cursor else {})})
        assert res.status_code == 200, res.text
        items += res.json()["items"]
        if not (cursor := res.json()["next_cursor"]):
            return items


def unseen(c: TestClient) -> int:
    return c.get("/inbox/unseen").json()["unseen"]


def test_received_serves_say_who_sent_what_and_when_newest_first(ann, bob, sent):
    (first, m1), (second, m2) = sent
    items = inbox(bob)
    assert [i["message_id"] for i in items] == [m2, m1]
    assert items[0]["sender"]["username"] == "ann" and items[0]["sent_at"]
    assert items[0]["serve"]["analysis_id"] == second and items[0]["serve"]["available"] is True
    assert items[0]["serve"]["thumbnail_url"] and items[0]["serve"]["overall_score"] == 77
    assert all(i["seen"] is False for i in items) and unseen(bob) == 2
    # Only what was sent to you: Ann's sent serves aren't in her own Received view.
    assert inbox(ann) == [] and unseen(ann) == 0


def test_opening_a_serve_marks_it_seen_for_you_alone(ann, bob, sent):
    (first, m1), _ = sent
    assert bob.get(f"/analyses/{first}").status_code == 200
    assert {i["message_id"]: i["seen"] for i in inbox(bob)}[m1] is True
    assert unseen(bob) == 1
    # Only the summary counts as opening it, and opening your own serve marks nothing.
    ann.get(f"/analyses/{first}")
    assert unseen(bob) == 1


def test_results_and_frames_alone_dont_mark_it_seen(bob, sent):
    _, (second, _) = sent
    bob.get(f"/analyses/{second}/result")
    bob.get(f"/analyses/{second}/frames")
    assert unseen(bob) == 2


def test_after_the_friendship_ends_they_stay_listed_but_unavailable(ann, bob, sent):
    ann.delete("/follows/bob")
    items = inbox(bob)
    assert len(items) == 2 and all(i["serve"]["available"] is False and i["serve"]["analysis_id"] is None for i in items)
    assert all(i["serve"]["thumbnail_url"] is None for i in items)
    assert unseen(bob) == 0  # nothing he could open, so nothing to badge


def test_a_deleted_message_or_serve_leaves_the_list(ann, bob, sent):
    (first, m1), (second, m2) = sent
    assert ann.delete(f"/messages/{m1}").status_code == 204
    assert [i["message_id"] for i in inbox(bob)] == [m2]
    assert ann.delete(f"/analyses/{second}").status_code == 204
    assert inbox(bob) == [] and unseen(bob) == 0


def test_hidden_people_are_left_out(app, ann, bob, sent):
    bob.post("/blocks", json={"username": "ann"})
    assert inbox(bob) == [] and unseen(bob) == 0
    bob.delete("/blocks/ann")
    db_of(app).suspend(ann.get("/auth/me").json()["id"], "test")
    assert inbox(bob) == [] and unseen(bob) == 0


def test_a_serve_still_processing_isnt_counted(app, settings, ann, bob):
    befriend(ann, bob, "bob")
    pending = finished(app, settings, ann, status="queued")
    conv = chat(ann, "bob")
    with db_of(app).engine.begin() as conn:  # sending only takes finished serves; put one in as if it had been
        conn.execute(messages.insert().values(id="m" * 32, conversation_id=conv, sender_id=ann.get("/auth/me").json()["id"],
                                              analysis_id=pending, created_at=now()))
    assert unseen(bob) == 0
    assert [i["serve"]["available"] for i in inbox(bob)] == [False]


@pytest.mark.parametrize("limit", [1, 2])
def test_pages_have_no_repeats_or_gaps(bob, sent, limit):
    assert [i["message_id"] for i in inbox(bob, limit)] == [i["message_id"] for i in inbox(bob)]


def test_bad_requests(app, bob):
    assert bob.get("/inbox", params={"cursor": "nonsense"}).status_code == 422
    assert bob.get("/inbox", params={"limit": 51}).status_code == 422
    assert TestClient(app).get("/inbox").status_code == 401
    assert TestClient(app).get("/inbox/unseen").status_code == 401


def test_the_data_download_has_when_you_opened_it_but_not_the_senders_side(ann, bob, sent):
    (first, _), _ = sent
    bob.get(f"/analyses/{first}")

    def opened(c):
        return [m.get("serve_opened_at") for conv in c.get("/auth/me/export").json()["conversations"] for m in conv["messages"]]
    assert sum(x is not None for x in opened(bob)) == 1
    assert all(x is None for x in opened(ann))


def test_serves_sent_before_the_upgrade_start_unseen(tmp_path):
    """Revision 0017 had no record of opening a serve: after the upgrade, they're all unseen."""
    url = Settings(data_dir=tmp_path).sqlalchemy_url  # SQLite, or the test Postgres (conftest.py)
    db = Database(url)
    command.upgrade(migrate.alembic_config(url), "0017")
    a, b = (db.create_user(f"{n}@example.com", "hash")["id"] for n in ("a", "b"))
    db.follow(a, b)
    db.follow(b, a)
    analysis_id = db.create(a, "right", "serve.mp4", "video/mp4", 1)["id"]
    with db.engine.begin() as conn:
        conn.execute(update(analyses).where(analyses.c.id == analysis_id).values(status="succeeded"))
    conv = db.conversation_with(a, b, create=True)["id"]
    old = Table("messages", MetaData(), autoload_with=db.engine)
    with db.engine.begin() as conn:
        conn.execute(insert(old).values(id="m1", conversation_id=conv, sender_id=a, analysis_id=analysis_id, created_at=now()))
    migrate.upgrade(db.engine)
    assert [m["id"] for m in db.received_serves(b, 10)] == ["m1"]
    assert db.unseen_serves(b) == 1
    assert db.mark_serve_seen(analysis_id, b) == 1 and db.unseen_serves(b) == 0
    # And back again: the column goes, the message stays.
    command.downgrade(migrate.alembic_config(url), "0017")
    assert "seen_at" not in {c["name"] for c in inspect(db.engine).get_columns("messages")}
    with db.engine.connect() as conn:
        assert conn.execute(Table("messages", MetaData(), autoload_with=db.engine).select()).first().id == "m1"

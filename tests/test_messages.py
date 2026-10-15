"""Messages between friends: who can send, reading, deleting, paging, blocks, reports, deletion and export."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from serve_api import worker
from serve_api.db import now
from serve_api.storage import LocalStorage
from serve_api.tables import user_reports
from tests.test_account import PASSWORD, app, client, db_of, mailer, settings, signup  # noqa: F401
from tests.test_follows import befriend, person


@pytest.fixture
def ann(app):
    return person(app, "ann")


@pytest.fixture
def bob(app):
    return person(app, "bob")


def chat(a: TestClient, name: str) -> str:
    res = a.post("/conversations", json={"username": name})
    assert res.status_code == 200, res.text
    return res.json()["id"]


def say(c: TestClient, conversation_id: str, text: str):
    return c.post(f"/conversations/{conversation_id}/messages", json={"body": text})


def bodies(c: TestClient, conversation_id: str) -> list:
    return [m["body"] for m in c.get(f"/conversations/{conversation_id}/messages").json()["items"]]


# --- who can message whom ------------------------------------------------------------------------

def test_friends_can_message_each_other(app, ann, bob):
    befriend(ann, bob, "bob")
    conv = chat(ann, "bob")
    assert chat(bob, "ann") == conv  # one conversation per pair, whoever opens it
    sent = say(ann, conv, "  Fancy a hit on Saturday?  ")
    assert sent.status_code == 201 and sent.json()["body"] == "Fancy a hit on Saturday?" and sent.json()["from_you"]
    assert say(bob, conv, "Yes! 10am?").status_code == 201
    assert bodies(ann, conv) == ["Yes! 10am?", "Fancy a hit on Saturday?"]  # newest first
    listed = ann.get("/conversations").json()
    assert len(listed) == 1 and listed[0]["person"]["username"] == "bob" and listed[0]["can_send"] is True
    assert listed[0]["last_message"] == {"text": "Yes! 10am?", "from_you": False, "deleted": False,
                                         "at": listed[0]["last_message"]["at"]}


def test_only_friends_can_start_a_conversation(app, ann, bob):
    res = ann.post("/conversations", json={"username": "bob"})
    assert res.status_code == 403 and res.json()["detail"] == "You can only message friends."
    assert ann.post("/conversations", json={"username": "ghost"}).status_code == 404
    assert ann.post("/conversations", json={"username": "ann"}).status_code == 404


def test_strangers_cant_read_or_write_someone_elses_conversation(app, ann, bob):
    befriend(ann, bob, "bob")
    conv = chat(ann, "bob")
    say(ann, conv, "private")
    eve = person(app, "eve")
    for res in (eve.get(f"/conversations/{conv}"), eve.get(f"/conversations/{conv}/messages"),
                say(eve, conv, "hi"), eve.post(f"/conversations/{conv}/read")):
        assert res.status_code == 404
    message_id = ann.get(f"/conversations/{conv}/messages").json()["items"][0]["id"]
    assert eve.delete(f"/messages/{message_id}").status_code == 404
    assert bob.delete(f"/messages/{message_id}").status_code == 404  # only the sender can delete it
    assert TestClient(app).get("/conversations").status_code == 401


def test_messages_are_checked(app, ann, bob):
    befriend(ann, bob, "bob")
    conv = chat(ann, "bob")
    assert say(ann, conv, "   \n  ").status_code == 422
    assert say(ann, conv, "x" * 2001).status_code == 422
    assert say(ann, conv, "x" * 2000).status_code == 201
    assert say(ann, conv, "line one\r\nline two\x07").json()["body"] == "line one\nline two"


def test_sending_is_rate_limited(app, ann, bob):
    befriend(ann, bob, "bob")
    conv = chat(ann, "bob")
    for i in range(30):
        assert say(ann, conv, f"{i}").status_code == 201
    assert say(ann, conv, "one too many").status_code == 429


# --- reading, deleting, paging -------------------------------------------------------------------

def test_unread_counts_and_seen(app, ann, bob):
    befriend(ann, bob, "bob")
    conv = chat(ann, "bob")
    say(ann, conv, "one")
    say(ann, conv, "two")
    assert bob.get("/conversations/unread").json() == {"unread": 2}
    assert ann.get("/conversations/unread").json() == {"unread": 0}  # your own don't count
    assert ann.get(f"/conversations/{conv}/messages").json()["seen_up_to"] is None
    assert bob.post(f"/conversations/{conv}/read").status_code == 204
    assert bob.get("/conversations/unread").json() == {"unread": 0}
    seen = ann.get(f"/conversations/{conv}/messages").json()["seen_up_to"]
    assert seen is not None and seen >= ann.get(f"/conversations/{conv}/messages").json()["items"][0]["created_at"]


def test_deleting_a_message_removes_it_for_everyone(app, ann, bob):
    befriend(ann, bob, "bob")
    conv = chat(ann, "bob")
    message_id = say(ann, conv, "oops, wrong chat").json()["id"]
    assert ann.delete(f"/messages/{message_id}").status_code == 204
    seen_by_bob = bob.get(f"/conversations/{conv}/messages").json()["items"][0]
    assert seen_by_bob["deleted"] is True and seen_by_bob["body"] is None
    assert bob.get("/conversations").json()[0]["last_message"]["text"] is None
    assert bob.get("/conversations/unread").json() == {"unread": 0}  # deleted ones don't count
    assert ann.delete(f"/messages/{message_id}").status_code == 404  # already gone


def test_older_messages_page_back(app, ann, bob):
    befriend(ann, bob, "bob")
    conv = chat(ann, "bob")
    for i in range(7):
        say(ann if i % 2 else bob, conv, f"m{i}")
    first = ann.get(f"/conversations/{conv}/messages", params={"limit": 3}).json()
    assert [m["body"] for m in first["items"]] == ["m6", "m5", "m4"]
    second = ann.get(f"/conversations/{conv}/messages", params={"limit": 3, "before": first["next_cursor"]}).json()
    assert [m["body"] for m in second["items"]] == ["m3", "m2", "m1"]
    third = ann.get(f"/conversations/{conv}/messages", params={"limit": 3, "before": second["next_cursor"]}).json()
    assert [m["body"] for m in third["items"]] == ["m0"] and third["next_cursor"] is None
    assert ann.get(f"/conversations/{conv}/messages", params={"before": "nonsense"}).status_code == 422


def test_an_opened_conversation_without_messages_isnt_listed(app, ann, bob):
    befriend(ann, bob, "bob")
    chat(ann, "bob")
    assert ann.get("/conversations").json() == [] and bob.get("/conversations").json() == []


# --- when friendships end ------------------------------------------------------------------------

def test_after_unfriending_the_conversation_stays_readable_but_closed(app, ann, bob):
    befriend(ann, bob, "bob")
    conv = chat(ann, "bob")
    say(ann, conv, "see you")
    ann.delete("/follows/bob")  # unfollowing ends the friendship
    assert bodies(bob, conv) == ["see you"]
    listed = bob.get("/conversations").json()[0]
    assert listed["can_send"] is False and listed["why_not"] == "You're no longer friends."
    assert say(bob, conv, "wait").status_code == 403
    # Friends again: it opens back up, with the history.
    befriend(ann, bob, "bob")
    assert say(bob, conv, "back!").status_code == 201 and chat(ann, "bob") == conv


def test_a_block_hides_the_conversation_from_both(app, ann, bob):
    befriend(ann, bob, "bob")
    conv = chat(ann, "bob")
    say(ann, conv, "hello")
    bob.post("/blocks", json={"username": "ann"})
    for c in (ann, bob):
        assert c.get("/conversations").json() == []
        assert c.get("/conversations/unread").json() == {"unread": 0}
        assert c.get(f"/conversations/{conv}/messages").status_code == 404
        assert say(c, conv, "hi").status_code == 404
    bob.delete("/blocks/ann")
    assert bodies(bob, conv) == ["hello"]  # back, but closed until they're friends again
    assert bob.get("/conversations").json()[0]["can_send"] is False


# --- reports -------------------------------------------------------------------------------------

def test_reporting_a_message_keeps_a_copy_for_review(app, ann, bob):
    befriend(ann, bob, "bob")
    conv = chat(ann, "bob")
    message_id = say(bob, conv, "something nasty").json()["id"]
    res = ann.post("/reports", json={"username": "bob", "message_id": message_id, "reason": "harassment",
                                     "note": "Third time this week."})
    assert res.status_code == 201
    bob.delete(f"/messages/{message_id}")  # deleting it doesn't remove the evidence
    stored = db_of(app).people_reports()
    assert len(stored) == 1
    assert (stored[0]["reported_username"], stored[0]["reason"], stored[0]["message_body"]) == (
        "bob", "harassment", "something nasty")


def test_you_can_only_report_messages_sent_to_you_by_that_person(app, ann, bob):
    befriend(ann, bob, "bob")
    conv = chat(ann, "bob")
    own = say(ann, conv, "mine").json()["id"]
    assert ann.post("/reports", json={"username": "bob", "message_id": own, "reason": "spam"}).status_code == 404
    eve = person(app, "eve")
    theirs = say(bob, conv, "to ann").json()["id"]
    assert eve.post("/reports", json={"username": "bob", "message_id": theirs, "reason": "spam"}).status_code == 404
    assert ann.post("/reports", json={"username": "bob", "reason": "nonsense"}).status_code == 422
    assert ann.post("/reports", json={"username": "ann", "reason": "spam"}).status_code == 404
    # Reporting a person, without a message, works even after blocking them.
    ann.post("/blocks", json={"username": "bob"})
    assert ann.post("/reports", json={"username": "bob", "reason": "impersonation"}).status_code == 201


def test_reports_are_limited_and_expire_after_a_year(app, settings, ann, bob):
    for _ in range(20):
        assert ann.post("/reports", json={"username": "bob", "reason": "spam"}).status_code == 201
    assert ann.post("/reports", json={"username": "bob", "reason": "spam"}).status_code == 429
    db = db_of(app)
    with db.engine.begin() as conn:
        conn.execute(user_reports.update().values(created_at=now() - worker.REPORTS_KEPT * 1.01))
    worker.housekeeping(db, LocalStorage(settings))
    with db.engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(user_reports)).scalar_one() == 0


# --- deletion and the data download --------------------------------------------------------------

def test_deleting_an_account_deletes_its_messages_but_not_the_other_side(app, ann, bob):
    befriend(ann, bob, "bob")
    conv = chat(ann, "bob")
    say(ann, conv, "from ann")
    say(bob, conv, "from bob")
    ann.post("/reports", json={"username": "bob", "reason": "spam"})
    bob.post("/reports", json={"username": "ann", "reason": "other"})
    assert bob.request("DELETE", "/auth/me", json={"password": PASSWORD}).status_code == 204
    assert bodies(ann, conv) == ["from ann"]
    listed = ann.get("/conversations").json()[0]
    assert listed["person"] is None and listed["can_send"] is False
    assert listed["why_not"] == "They've deleted their account."
    # Reports stay for review, without Bob's account id.
    rows = db_of(app).people_reports()
    assert len(rows) == 2 and all(None in (r["reporter_id"], r["reported_id"]) for r in rows)


def test_the_data_download_has_your_conversations_and_reports(app, ann, bob):
    befriend(ann, bob, "bob")
    conv = chat(ann, "bob")
    say(ann, conv, "hi bob")
    deleted = say(ann, conv, "never mind").json()["id"]
    ann.delete(f"/messages/{deleted}")
    say(bob, conv, "hi ann")
    ann.post("/reports", json={"username": "bob", "reason": "other", "note": "test"})
    data = ann.get("/auth/me/export").json()
    assert data["conversations"][0]["with_username"] == "bob"
    assert [(m["from_you"], m["body"], m["deleted"]) for m in data["conversations"][0]["messages"]] == [
        (True, "hi bob", False), (True, None, True), (False, "hi ann", False)]
    assert data["reports_made"][0]["username"] == "bob" and data["reports_made"][0]["note"] == "test"
    assert bob.get("/auth/me/export").json()["reports_made"] == []

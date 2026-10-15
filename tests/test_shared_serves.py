"""Sending a serve to a friend: who can open it, read-only, and how access ends."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from serve_api import keys
from serve_api.storage import LocalStorage
from serve_api.tables import analyses
from tests.test_account import PASSWORD, app, client, create_analysis, db_of, mailer, signup  # noqa: F401
from tests.test_connections import befriend, person
from tests.test_existing_data import schema_2_results
from tests.test_messages import chat


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


def finished(app, settings, c: TestClient, filename="secret-session.mp4", status="succeeded") -> str:
    """A finished analysis with its results and frames files, and a note on it."""
    analysis_id = c.post("/analyses", json={"hand": "right", "filename": filename, "content_type": "video/mp4",
                                            "size_bytes": 1}).json()["analysis"]["id"]
    storage = LocalStorage(settings)
    results = schema_2_results()  # the demo serve's real output
    for name, data in ((keys.RESULTS, json.dumps(results)), (keys.FRAMES, "{}"), (keys.THUMBNAIL, "jpg")):
        path = storage.path(keys.output_key(analysis_id, name))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
    with db_of(app).engine.begin() as conn:
        conn.execute(update(analyses).where(analyses.c.id == analysis_id).values(
            status=status, overall_score=77, note="Private: my coach says I'm hopeless"))
    return analysis_id


def send(c: TestClient, conversation_id: str, analysis_id: str, body: str | None = None):
    return c.post(f"/conversations/{conversation_id}/messages", json={"body": body, "analysis_id": analysis_id})


def can_open(c: TestClient, analysis_id: str) -> bool:
    codes = {c.get(f"/analyses/{analysis_id}{p}").status_code for p in ("", "/result", "/frames")}
    assert len(codes) == 1, codes  # all three agree
    return codes == {200}


@pytest.fixture
def shared(app, settings, ann, bob):
    """Ann sends Bob one of her serves. Returns (analysis id, conversation id, message id)."""
    befriend(ann, bob, "bob")
    analysis_id = finished(app, settings, ann)
    conv = chat(ann, "bob")
    res = send(ann, conv, analysis_id, "Look at my knee bend!")
    assert res.status_code == 201, res.text
    return analysis_id, conv, res.json()["id"]


# --- sending -------------------------------------------------------------------------------------

def test_a_sent_serve_shows_in_the_conversation(app, ann, bob, shared):
    analysis_id, conv, _ = shared
    seen = bob.get(f"/conversations/{conv}/messages").json()["items"][0]
    assert seen["body"] == "Look at my knee bend!"
    assert seen["serve"]["analysis_id"] == analysis_id and seen["serve"]["available"] is True
    assert seen["serve"]["overall_score"] == 77 and seen["serve"]["thumbnail_url"]


def test_a_serve_can_be_sent_without_text(app, settings, ann, bob, shared):
    _, conv, _ = shared
    other = finished(app, settings, ann)
    res = send(ann, conv, other)
    assert res.status_code == 201 and res.json()["body"] is None and res.json()["serve"]["available"]
    assert bob.get("/conversations").json()[0]["last_message"]["text"] == "Sent a serve"
    assert ann.post(f"/conversations/{conv}/messages", json={}).status_code == 422


def test_only_your_own_finished_serves_can_be_sent(app, settings, ann, bob, shared):
    analysis_id, conv, _ = shared
    # Bob can't forward Ann's serve, even though he can open it.
    assert send(bob, conv, analysis_id).status_code == 404
    unfinished = finished(app, settings, ann, status="failed")
    assert send(ann, conv, unfinished).status_code == 404
    assert send(ann, conv, "0" * 32).status_code == 404


# --- opening it ----------------------------------------------------------------------------------

def test_the_friend_can_open_it_read_only_without_the_note_or_filename(app, ann, bob, shared):
    analysis_id, _, _ = shared
    assert can_open(bob, analysis_id)
    summary = bob.get(f"/analyses/{analysis_id}").json()
    assert summary["note"] is None and summary["filename"] == "Shared serve"
    assert summary["shared_by"]["username"] == "ann"
    assert "secret-session" not in bob.get(f"/analyses/{analysis_id}/result").text
    # The owner sees their own, unchanged.
    mine = ann.get(f"/analyses/{analysis_id}").json()
    assert mine["filename"] == "secret-session.mp4" and mine["note"] and mine["shared_by"] is None


def test_the_friend_cant_change_anything(app, ann, bob, shared):
    analysis_id, _, _ = shared
    for res in (bob.put(f"/analyses/{analysis_id}/note", json={"note": "mine now"}),
                bob.delete(f"/analyses/{analysis_id}"),
                bob.put(f"/analyses/{analysis_id}/report", json={"reason": "wrong_phases"}),
                bob.get(f"/analyses/{analysis_id}/report"),
                bob.post(f"/analyses/{analysis_id}/retry"),
                bob.post(f"/analyses/{analysis_id}/start")):
        assert res.status_code == 404, res.request.url
    assert ann.get(f"/analyses/{analysis_id}").status_code == 200  # still there
    assert analysis_id not in [a["id"] for a in bob.get("/analyses").json()["items"]]  # not in his serves
    assert bob.get("/auth/me/export").json()["analyses"] == []  # nor his data download


def test_nobody_else_can_open_it(app, ann, bob, shared):
    analysis_id, _, _ = shared
    eve = person(app, "eve")
    befriend(ann, eve, "eve")  # a friend of Ann's, but it wasn't sent to her
    assert not can_open(eve, analysis_id)
    assert TestClient(app).get(f"/analyses/{analysis_id}").status_code == 401


# --- how access ends -----------------------------------------------------------------------------

def test_deleting_the_message_stops_sharing(app, ann, bob, shared):
    analysis_id, conv, message_id = shared
    ann.delete(f"/messages/{message_id}")
    assert not can_open(bob, analysis_id)
    seen = bob.get(f"/conversations/{conv}/messages").json()["items"][0]
    assert seen["deleted"] is True and seen["serve"] is None


def test_unfriending_stops_sharing_and_refriending_restores_it(app, ann, bob, shared):
    analysis_id, conv, _ = shared
    friendship = bob.get("/connections").json()["friends"][0]["id"]
    bob.delete(f"/connections/{friendship}")
    assert not can_open(bob, analysis_id)
    assert bob.get(f"/conversations/{conv}/messages").json()["items"][0]["serve"] == {
        "analysis_id": None, "available": False, "overall_score": None, "recorded_at": None, "thumbnail_url": None}
    befriend(ann, bob, "bob")
    assert can_open(bob, analysis_id)


def test_a_block_stops_sharing(app, ann, bob, shared):
    analysis_id, _, _ = shared
    ann.post("/blocks", json={"username": "bob"})
    assert not can_open(bob, analysis_id)


def test_deleting_the_analysis_leaves_a_marker_in_the_message(app, ann, bob, shared):
    analysis_id, conv, _ = shared
    assert ann.delete(f"/analyses/{analysis_id}").status_code == 204
    assert not can_open(bob, analysis_id)
    seen = bob.get(f"/conversations/{conv}/messages").json()["items"][0]
    assert seen["body"] == "Look at my knee bend!" and seen["serve"] is None  # the link is gone with it
    assert ann.get(f"/conversations/{conv}/messages").json()["items"][0]["serve"] is None


def test_deleting_the_senders_account_ends_it(app, ann, bob, shared):
    analysis_id, conv, _ = shared
    assert ann.request("DELETE", "/auth/me", json={"password": PASSWORD}).status_code == 204
    assert not can_open(bob, analysis_id)
    assert bob.get(f"/conversations/{conv}/messages").json()["items"] == []


def test_the_senders_data_download_lists_the_serves_sent(app, ann, shared):
    analysis_id, _, _ = shared
    messages = ann.get("/auth/me/export").json()["conversations"][0]["messages"]
    assert messages[0]["serve"] == analysis_id

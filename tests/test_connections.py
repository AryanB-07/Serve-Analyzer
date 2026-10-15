"""Friends: finding people, requests, friendships, blocks, privacy, deletion and the data download."""

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.test_account import PASSWORD, app, client, db_of, mailer, settings, signup  # noqa: F401


def person(app, username: str | None = None) -> TestClient:
    """A signed-in account, with ``username`` set if given."""
    c = TestClient(app)
    signup(c)
    if username:
        assert c.patch("/profile", json={"username": username}).status_code == 200
    return c


def befriend(a: TestClient, b: TestClient, b_name: str) -> str:
    sent = a.post("/connections", json={"username": b_name})
    assert sent.status_code == 201, sent.text
    incoming = b.get("/connections").json()["incoming"]
    assert b.post(f"/connections/{incoming[0]['id']}/accept").status_code == 200
    return incoming[0]["id"]


@pytest.fixture
def ann(app):
    return person(app, "ann")


@pytest.fixture
def bob(app):
    return person(app, "bob")


# --- finding people ------------------------------------------------------------------------------

def test_finding_someone_by_username_shows_only_the_basics(app, ann, bob):
    bob.patch("/profile", json={"display_name": "Bob B", "bio": "Lefty."})
    seen = ann.get("/people/BOB").json()
    assert seen == {"username": "bob", "display_name": "Bob B", "avatar_url": None, "relationship": "none",
                    "connection_id": None, "can_request": True, "bio": None, "friends_since": None,
                    "stats": None, "positions": None}
    assert ann.get("/people/@bob").status_code == 200  # a leading @ is fine
    assert ann.get("/people/nobody_here").status_code == 404
    assert ann.get("/people/ann").json()["relationship"] == "self"


def test_finding_people_needs_signing_in(app, bob):
    assert TestClient(app).get("/people/bob").status_code == 401
    assert TestClient(app).get("/connections").status_code == 401


def test_no_email_or_private_data_is_ever_shown_to_others(app, ann, bob):
    bob_email = bob.get("/auth/me").json()["email"]
    befriend(ann, bob, "bob")
    for path in ("/people/bob", "/connections", "/blocks"):
        assert bob_email not in ann.get(path).text


# --- requests and friendships --------------------------------------------------------------------

def test_a_request_accepted_makes_friends_and_friends_see_the_bio(app, ann, bob):
    bob.patch("/profile", json={"bio": "Working on my kick serve."})
    res = ann.post("/connections", json={"username": "bob"})
    assert res.status_code == 201 and res.json()["relationship"] == "requested"
    assert bob.get("/connections/count").json() == {"incoming": 1}
    assert bob.get("/people/ann").json()["relationship"] == "incoming"
    listing = bob.get("/connections").json()
    assert [c["person"]["username"] for c in listing["incoming"]] == ["ann"]
    assert ann.get("/connections").json()["outgoing"][0]["person"]["username"] == "bob"

    accepted = bob.post(f"/connections/{listing['incoming'][0]['id']}/accept")
    assert accepted.status_code == 200 and accepted.json()["status"] == "accepted"
    assert bob.get("/connections/count").json() == {"incoming": 0}
    seen = ann.get("/people/bob").json()
    assert seen["relationship"] == "friends" and seen["bio"] == "Working on my kick serve."
    assert seen["friends_since"] is not None
    assert [c["person"]["username"] for c in ann.get("/connections").json()["friends"]] == ["bob"]


def test_asking_someone_who_already_asked_you_makes_you_friends(app, ann, bob):
    ann.post("/connections", json={"username": "bob"})
    res = bob.post("/connections", json={"username": "ann"})
    assert res.status_code == 200 and res.json()["relationship"] == "friends"
    assert len(ann.get("/connections").json()["friends"]) == 1


def test_duplicate_and_odd_requests_are_refused(app, ann, bob):
    assert ann.post("/connections", json={"username": "ann"}).status_code == 400
    assert ann.post("/connections", json={"username": "ghost"}).status_code == 404
    ann.post("/connections", json={"username": "bob"})
    again = ann.post("/connections", json={"username": "bob"})
    assert again.status_code == 409 and "already sent" in again.json()["detail"]
    befriend_id = bob.get("/connections").json()["incoming"][0]["id"]
    bob.post(f"/connections/{befriend_id}/accept")
    assert "already friends" in ann.post("/connections", json={"username": "bob"}).json()["detail"]


def test_you_need_a_username_to_send_requests(app, bob):
    anonymous = person(app)
    res = anonymous.post("/connections", json={"username": "bob"})
    assert res.status_code == 409 and "Choose a username first" in res.json()["detail"]
    # ...but you can still be found once you have one, and look people up.
    assert anonymous.get("/people/bob").status_code == 200


def test_only_the_person_asked_can_accept(app, ann, bob):
    ann.post("/connections", json={"username": "bob"})
    request_id = bob.get("/connections").json()["incoming"][0]["id"]
    assert ann.post(f"/connections/{request_id}/accept").status_code == 404  # the sender can't
    carol = person(app, "carol")
    assert carol.post(f"/connections/{request_id}/accept").status_code == 404  # nor a stranger
    assert carol.delete(f"/connections/{request_id}").status_code == 404
    assert bob.get("/connections/count").json() == {"incoming": 1}


def test_cancelling_declining_and_unfriending(app, ann, bob):
    ann.post("/connections", json={"username": "bob"})
    request_id = ann.get("/connections").json()["outgoing"][0]["id"]
    assert ann.delete(f"/connections/{request_id}").status_code == 204  # cancel
    assert bob.get("/connections/count").json() == {"incoming": 0}

    ann.post("/connections", json={"username": "bob"})
    request_id = bob.get("/connections").json()["incoming"][0]["id"]
    assert bob.delete(f"/connections/{request_id}").status_code == 204  # decline
    assert ann.get("/people/bob").json()["relationship"] == "none"

    friendship = befriend(ann, bob, "bob")
    assert bob.delete(f"/connections/{friendship}").status_code == 204  # unfriend
    seen = ann.get("/people/bob").json()
    assert seen["relationship"] == "none" and seen["bio"] is None


def test_someone_can_stop_accepting_requests(app, ann, bob):
    assert bob.patch("/profile", json={"accept_requests": False}).json()["accept_requests"] is False
    assert ann.get("/people/bob").json()["can_request"] is False
    res = ann.post("/connections", json={"username": "bob"})
    assert res.status_code == 403 and "aren't accepting" in res.json()["detail"]
    # They can still send requests themselves.
    assert bob.post("/connections", json={"username": "ann"}).status_code == 201
    assert bob.patch("/profile", json={"accept_requests": None}).status_code == 422


def test_requests_are_rate_limited(app, ann):
    db = db_of(app)
    names = [f"p{uuid.uuid4().hex[:8]}" for _ in range(31)]
    for name in names:  # made directly: signing up 31 accounts would hit the per-IP signup limit
        user = db.create_user(f"{name}@example.com", "hash")
        db.save_profile(user["id"], username=name)
    for name in names[:30]:
        assert ann.post("/connections", json={"username": name}).status_code == 201
    assert ann.post("/connections", json={"username": names[30]}).status_code == 429


# --- blocking ------------------------------------------------------------------------------------

def test_blocking_ends_everything_and_hides_you_both_ways(app, ann, bob):
    befriend(ann, bob, "bob")
    assert bob.post("/blocks", json={"username": "ann"}).status_code == 204
    assert bob.get("/connections").json()["friends"] == []
    assert ann.get("/connections").json()["friends"] == []
    # To Ann, Bob doesn't exist: the same answer as a username nobody has.
    for res in (ann.get("/people/bob"), ann.post("/connections", json={"username": "bob"}),
                ann.post("/blocks", json={"username": "bob"})):
        assert res.status_code == 404 and res.json()["detail"] == "No one has that username."
    # And Bob doesn't see Ann either, until he unblocks.
    assert bob.get("/people/ann").status_code == 404
    assert [b["person"]["username"] for b in bob.get("/blocks").json()] == ["ann"]
    assert bob.delete("/blocks/ann").status_code == 204
    assert ann.get("/people/bob").json()["relationship"] == "none"
    assert bob.delete("/blocks/ann").status_code == 404


def test_a_blocked_persons_pending_request_disappears(app, ann, bob):
    ann.post("/connections", json={"username": "bob"})
    bob.post("/blocks", json={"username": "ann"})
    assert bob.get("/connections/count").json() == {"incoming": 0}
    assert ann.get("/connections").json()["outgoing"] == []


def test_blocks_are_private_to_the_blocker(app, ann, bob):
    bob.post("/blocks", json={"username": "ann"})
    assert ann.get("/blocks").json() == []
    assert ann.delete("/blocks/ann").status_code == 404


# --- deletion and the data download --------------------------------------------------------------

def test_the_data_download_lists_friends_requests_and_blocks(app, ann, bob):
    befriend(ann, bob, "bob")
    carol = person(app, "carol")
    carol.post("/connections", json={"username": "ann"})
    person(app, "dave")
    ann.post("/blocks", json={"username": "dave"})
    data = ann.get("/auth/me/export").json()
    assert {(c["username"], c["status"], c["direction"]) for c in data["connections"]} == {
        ("bob", "accepted", "outgoing"), ("carol", "pending", "incoming")}
    assert [b["username"] for b in data["blocks"]] == ["dave"]


def test_deleting_an_account_removes_its_friendships_requests_and_blocks(app, ann, bob):
    befriend(ann, bob, "bob")
    carol = person(app, "carol")
    carol.post("/connections", json={"username": "bob"})
    bob.post("/blocks", json={"username": "ann"})
    assert bob.request("DELETE", "/auth/me", json={"password": PASSWORD}).status_code == 204
    assert ann.get("/connections").json() == {"friends": [], "incoming": [], "outgoing": []}
    assert carol.get("/connections").json()["outgoing"] == []
    assert ann.get("/people/bob").status_code == 404
    # Bob's block went with him, and his username is free again.
    assert person(app, "bob").get("/people/ann").status_code == 200

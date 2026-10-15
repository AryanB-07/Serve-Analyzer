"""Following, friends as mutual follows, removing followers, blocks, privacy, deletion, the data
download, and converting a database from friend requests."""

import uuid
from datetime import timedelta

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, Table, insert, select

from serve_api import migrate
from serve_api.auth import SESSION_COOKIE, hash_token
from serve_api.db import Database, now
from serve_api.settings import Settings
from serve_api.tables import follows
from tests.test_account import PASSWORD, app, client, db_of, mailer, settings, signup  # noqa: F401


def person(app, username: str | None = None) -> TestClient:
    """A signed-in account, with ``username`` set if given."""
    c = TestClient(app)
    signup(c)
    if username:
        assert c.patch("/profile", json={"username": username}).status_code == 200
    return c


def username_of(c: TestClient) -> str:
    return c.get("/profile").json()["username"]


def befriend(a: TestClient, b: TestClient, b_name: str | None = None) -> None:
    """Make two accounts friends: each follows the other."""
    b_name = b_name or username_of(b)
    assert a.put(f"/follows/{b_name}").status_code == 200
    assert b.put(f"/follows/{username_of(a)}").status_code == 200


def rel(c: TestClient, name: str) -> str:
    return c.get(f"/people/{name}").json()["relationship"]


def names(entries: list) -> list:
    return [e["person"]["username"] for e in entries]


def walk(c: TestClient, name: str, kind: str, limit: int = 2) -> list:
    """Every entry of someone's list, page by page."""
    items, cursor = [], None
    while True:
        res = c.get(f"/people/{name}/{kind}", params={"limit": limit, **({"cursor": cursor} if cursor else {})})
        assert res.status_code == 200, res.text
        items += res.json()["items"]
        if not (cursor := res.json()["next_cursor"]):
            return items


def legacy_account(app) -> TestClient:
    """An account from before usernames were required at signup."""
    db = db_of(app)
    user = db.create_user(f"old{uuid.uuid4().hex[:8]}@example.com", "hash")
    token = uuid.uuid4().hex
    db.create_session(user["id"], hash_token(token), now() + timedelta(days=1))
    c = TestClient(app)
    c.cookies.set(SESSION_COOKIE, token)
    return c


@pytest.fixture
def ann(app):
    return person(app, "ann")


@pytest.fixture
def bob(app):
    return person(app, "bob")


# --- following and friends -----------------------------------------------------------------------

def test_following_is_one_way_until_its_returned(app, ann, bob):
    assert rel(ann, "bob") == "none"
    res = ann.put("/follows/bob")
    assert res.status_code == 200 and res.json()["relationship"] == "following"
    assert rel(bob, "ann") == "follows_you"
    assert bob.get("/people/ann").json()["can_follow"] is True  # "Follow back"
    assert bob.put("/follows/ann").json()["relationship"] == "friends"
    assert rel(ann, "bob") == "friends"


def test_friends_see_each_others_bio_and_since_when(app, ann, bob):
    bob.patch("/profile", json={"bio": "Lefty."})
    ann.put("/follows/bob")
    assert ann.get("/people/bob").json()["bio"] is None  # following isn't enough
    bob.put("/follows/ann")
    seen = ann.get("/people/bob").json()
    assert seen["bio"] == "Lefty." and seen["friends_since"] is not None


def test_unfollowing_a_friend_ends_the_friendship(app, ann, bob):
    befriend(ann, bob, "bob")
    assert ann.delete("/follows/bob").status_code == 204
    assert rel(ann, "bob") == "follows_you" and rel(bob, "ann") == "following"
    assert ann.get("/follows").json() == {"followers": 1, "following": 0, "friends": 0}


def test_removing_a_follower(app, ann, bob):
    befriend(ann, bob, "bob")
    assert bob.delete("/followers/ann").status_code == 204
    assert rel(bob, "ann") == "following"  # Bob still follows Ann
    assert names(walk(bob, "bob", "followers")) == []
    assert bob.delete("/followers/ann").status_code == 204  # already gone: fine


def test_follow_and_unfollow_are_idempotent(app, ann, bob):
    for _ in range(3):
        assert ann.put("/follows/bob").status_code == 200
    with db_of(app).engine.connect() as conn:
        assert len(conn.execute(select(follows)).all()) == 1
    assert bob.get("/follows").json()["followers"] == 1
    for _ in range(2):
        assert ann.delete("/follows/bob").status_code == 204
    assert bob.get("/follows").json()["followers"] == 0


def test_the_database_refuses_duplicates_and_self_follows(app, ann, bob):
    db = db_of(app)
    ann_id, bob_id = (c.get("/auth/me").json()["id"] for c in (ann, bob))
    assert db.follow(ann_id, bob_id) is True and db.follow(ann_id, bob_id) is False
    with pytest.raises(ValueError):
        db.follow(ann_id, ann_id)
    with pytest.raises(Exception), db.engine.begin() as conn:  # the check constraint, below the API
        conn.execute(insert(follows).values(follower_id=ann_id, followee_id=ann_id, created_at=now()))


def test_odd_follows_are_refused(app, ann):
    assert ann.put("/follows/ann").status_code == 400
    assert ann.put("/follows/ghost").status_code == 404
    assert ann.delete("/follows/ghost").status_code == 404
    assert TestClient(app).put("/follows/ann").status_code == 401


def test_you_need_a_username_to_follow(app, bob):
    anonymous = legacy_account(app)
    assert anonymous.get("/profile").json()["username"] is None
    res = anonymous.put("/follows/bob")
    assert res.status_code == 409 and "Choose a username first" in res.json()["detail"]


def test_lists_and_counts(app, ann, bob):
    carol, dave = person(app, "carol"), person(app, "dave")
    befriend(ann, bob, "bob")
    carol.put("/follows/ann")  # a follower
    ann.put("/follows/dave")  # following
    assert ann.get("/follows").json() == {"followers": 2, "following": 2, "friends": 1}
    assert names(walk(ann, "ann", "friends")) == ["bob"]
    assert sorted(names(walk(ann, "ann", "followers"))) == ["bob", "carol"]
    assert sorted(names(walk(ann, "ann", "following"))) == ["bob", "dave"]
    carol_entry = next(e for e in walk(ann, "ann", "followers") if e["person"]["username"] == "carol")
    assert carol_entry["follows_you"] is True and carol_entry["you_follow"] is False
    # Counts show on anyone's page.
    assert dave.get("/people/ann").json()["counts"] == {"followers": 2, "following": 2, "friends": 1}


def test_only_you_and_your_friends_can_see_your_lists(app, ann, bob):
    carol, dave = person(app, "carol"), person(app, "dave")
    befriend(ann, bob, "bob")
    carol.put("/follows/ann")  # Carol follows Ann; Ann doesn't follow back
    ann.put("/follows/dave")  # Ann follows Dave; Dave doesn't follow back
    eve = person(app, "eve")  # a stranger
    for kind in ("friends", "followers", "following"):
        assert ann.get(f"/people/ann/{kind}").status_code == 200
        assert bob.get(f"/people/ann/{kind}").status_code == 200  # a friend
        for outsider in (carol, dave, eve):  # one-way either direction, or nothing
            res = outsider.get(f"/people/ann/{kind}")
            assert res.status_code == 403 and "Only friends" in res.json()["detail"]
    assert bob.get("/people/ann").json()["can_see_lists"] is True
    assert carol.get("/people/ann").json()["can_see_lists"] is False
    assert ann.get("/people/ghost/friends").status_code == 404
    assert ann.get("/people/ann/enemies").status_code == 422
    # A friend's view says how the viewer stands with each person on it.
    entry = next(e for e in walk(bob, "ann", "followers") if e["person"]["username"] == "carol")
    assert entry["you_follow"] is False and entry["follows_you"] is False


def test_lists_page_without_repeats_or_gaps(app, ann):
    db = db_of(app)
    ann_id = ann.get("/auth/me").json()["id"]
    made = []
    for i in range(7):
        user = db.create_user(f"f{i}{uuid.uuid4().hex[:6]}@example.com", "hash")
        db.save_profile(user["id"], username=f"fan{i}{uuid.uuid4().hex[:4]}")
        db.follow(user["id"], ann_id)
        if i % 2 == 0:
            db.follow(ann_id, user["id"])  # some of them are friends
        made.append(user["id"])
    for kind, expected in (("followers", 7), ("friends", 4), ("following", 4)):
        for limit in (1, 2, 3, 100):
            seen = names(walk(ann, "ann", kind, limit))
            assert len(seen) == expected == len(set(seen)), (kind, limit)
    first = ann.get("/people/ann/followers", params={"limit": 3}).json()
    assert len(first["items"]) == 3 and first["next_cursor"]
    assert ann.get("/people/ann/followers", params={"limit": 101}).status_code == 422
    assert ann.get("/people/ann/followers", params={"cursor": "nonsense"}).status_code == 422


def test_a_friends_lists_leave_out_people_hidden_from_you(app, ann, bob):
    carol = person(app, "carol")
    befriend(ann, bob, "bob")
    carol.put("/follows/bob")
    carol.post("/blocks", json={"username": "ann"})  # Carol blocked Ann
    assert "carol" not in names(walk(ann, "bob", "followers"))
    assert "carol" in names(walk(bob, "bob", "followers"))


def test_someone_can_stop_new_followers_but_people_they_follow_can_follow_back(app, ann, bob):
    bob.patch("/profile", json={"allow_follows": False})
    assert ann.get("/people/bob").json()["can_follow"] is False
    res = ann.put("/follows/bob")
    assert res.status_code == 403 and "new followers" in res.json()["detail"]
    bob.put("/follows/ann")  # Bob follows Ann...
    assert ann.get("/people/bob").json()["can_follow"] is True
    assert ann.put("/follows/bob").json()["relationship"] == "friends"  # ...so she can follow back


def test_new_follows_are_rate_limited(app, ann):
    db = db_of(app)
    names_ = [f"p{uuid.uuid4().hex[:8]}" for _ in range(61)]
    for name in names_:  # made directly: signing up 61 accounts would hit the per-IP signup limit
        user = db.create_user(f"{name}@example.com", "hash")
        db.save_profile(user["id"], username=name)
    for name in names_[:60]:
        assert ann.put(f"/follows/{name}").status_code == 200
    assert ann.put(f"/follows/{names_[60]}").status_code == 429


# --- blocks and suspensions ----------------------------------------------------------------------

def test_blocking_removes_the_follows_both_ways_and_hides_you(app, ann, bob):
    befriend(ann, bob, "bob")
    bob.post("/blocks", json={"username": "ann"})
    assert ann.get("/follows").json() == {"followers": 0, "following": 0, "friends": 0}
    for res in (ann.get("/people/bob"), ann.put("/follows/bob"), ann.delete("/follows/bob")):
        assert res.status_code == 404 and res.json()["detail"] == "No one has that username."
    assert bob.get("/people/ann").status_code == 404
    bob.delete("/blocks/ann")
    assert rel(ann, "bob") == "none"  # unblocking doesn't bring the follows back


def test_suspended_accounts_leave_lists_and_counts(app, ann, bob):
    befriend(ann, bob, "bob")
    bob_id = bob.get("/auth/me").json()["id"]
    db_of(app).suspend(bob_id, "test")
    assert ann.get("/follows").json() == {"followers": 0, "following": 0, "friends": 0}
    assert ann.get("/people/bob").status_code == 404
    db_of(app).unsuspend(bob_id)
    assert rel(ann, "bob") == "friends"


def test_no_email_or_private_data_is_shown_to_others(app, ann, bob):
    bob_email = bob.get("/auth/me").json()["email"]
    befriend(ann, bob, "bob")
    for path in ("/people/bob", "/follows", "/blocks"):
        assert bob_email not in ann.get(path).text


# --- deletion, the data download and existing data -----------------------------------------------

def test_the_data_download_lists_follows_and_blocks(app, ann, bob):
    befriend(ann, bob, "bob")
    person(app, "carol").put("/follows/ann")
    person(app, "dave")
    ann.post("/blocks", json={"username": "dave"})
    data = ann.get("/auth/me/export").json()
    assert sorted(f["username"] for f in data["followers"]) == ["bob", "carol"]
    assert [f["username"] for f in data["following"]] == ["bob"]
    assert [b["username"] for b in data["blocks"]] == ["dave"]


def test_deleting_an_account_removes_its_follows(app, ann, bob):
    befriend(ann, bob, "bob")
    bob.request("DELETE", "/auth/me", json={"password": PASSWORD})
    assert ann.get("/follows").json() == {"followers": 0, "following": 0, "friends": 0}
    assert ann.get("/people/bob").status_code == 404


def test_friend_requests_become_follows_when_the_database_is_upgraded(tmp_path):
    """Revision 0015 had friend requests: a friendship becomes two follows, a pending request one."""
    settings = Settings(data_dir=tmp_path)  # SQLite, or the test Postgres (conftest.py)
    db = Database(settings.sqlalchemy_url)
    command.upgrade(migrate.alembic_config(settings.sqlalchemy_url), "0015")
    ids = [db.create_user(f"{n}@example.com", "hash")["id"] for n in ("a", "b", "c")]
    old = Table("connections", MetaData(), autoload_with=db.engine)
    profiles = Table("profiles", MetaData(), autoload_with=db.engine)
    notifications = Table("notifications", MetaData(), autoload_with=db.engine)
    with db.engine.begin() as conn:
        conn.execute(insert(old).values(id="c1", requester_id=ids[0], addressee_id=ids[1], pair=":".join(sorted(ids[:2])),
                                        status="accepted", created_at=now(), accepted_at=now()))
        conn.execute(insert(old).values(id="c2", requester_id=ids[2], addressee_id=ids[0], pair=":".join(sorted((ids[0], ids[2]))),
                                        status="pending", created_at=now(), accepted_at=None))
        conn.execute(insert(profiles).values(user_id=ids[0], username="a", accept_requests=False, updated_at=now()))
        conn.execute(insert(notifications).values(id="n1", user_id=ids[0], kind="request_received", actor_id=ids[2],
                                                  created_at=now()))
    migrate.upgrade(db.engine)
    assert db.are_friends(ids[0], ids[1])
    assert db.follow_row(ids[2], ids[0]) is not None and not db.are_friends(ids[0], ids[2])
    assert db.get_profile(ids[0])["allow_follows"] is False
    assert db.notifications_for(ids[0])[0]["kind"] == "new_follower"
    # And back again.
    command.downgrade(migrate.alembic_config(settings.sqlalchemy_url), "0015")
    with db.engine.connect() as conn:
        rows = {r.status for r in conn.execute(select(Table("connections", MetaData(), autoload_with=db.engine)))}
    assert rows == {"accepted", "pending"}


# --- usernames at signup -------------------------------------------------------------------------

def signup_with(client: TestClient, username, email: str | None = None):
    body = {"email": email or f"{uuid.uuid4().hex[:10]}@example.com", "password": PASSWORD, "accept_terms": True}
    if username is not None:
        body["username"] = username
    return client.post("/auth/signup", json=body)


def test_signing_up_needs_a_valid_username(app):
    assert signup_with(TestClient(app), None).status_code == 422
    for bad in ("ab", "has space", "admin"):
        assert signup_with(TestClient(app), bad).status_code == 422
    c = TestClient(app)
    assert signup_with(c, "  @New_Player ").status_code == 201
    assert c.get("/profile").json()["username"] == "new_player"


def test_a_taken_or_held_username_is_refused_at_signup(app, ann):
    res = signup_with(TestClient(app), "ANN")
    assert res.status_code == 409 and res.json()["detail"] == "That username is taken."
    ann.patch("/profile", json={"username": "ann_renamed"})
    res = signup_with(TestClient(app), "ann")  # held for Ann for 30 days
    assert res.status_code == 409 and "held" in res.json()["detail"]
    # The email isn't used up by a refused signup.
    email = "keeps@example.com"
    assert signup_with(TestClient(app), "ann", email).status_code == 409
    assert signup_with(TestClient(app), "fresh_name", email).status_code == 201


def test_a_deleted_accounts_username_stays_held_for_newcomers(app):
    c = TestClient(app)
    signup_with(c, "gone_soon")
    c.request("DELETE", "/auth/me", json={"password": PASSWORD})
    assert signup_with(TestClient(app), "gone_soon").status_code == 409


def test_the_signup_form_can_check_a_username_signed_out(app, ann):
    c = TestClient(app)
    assert c.get("/auth/username-check", params={"username": "Ann"}).json() == {
        "username": "ann", "available": False, "problem": "That username is taken."}
    assert c.get("/auth/username-check", params={"username": "free_one"}).json()["available"] is True
    assert c.get("/auth/username-check", params={"username": "x"}).json()["available"] is False
    for _ in range(118):
        c.get("/auth/username-check", params={"username": "free_one"})
    assert c.get("/auth/username-check", params={"username": "free_one"}).status_code == 429

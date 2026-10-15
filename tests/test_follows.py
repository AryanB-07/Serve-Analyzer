"""Following, friends as mutual follows, removing followers, blocks, privacy, deletion, the data
download, and converting a database from friend requests."""

import uuid

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, Table, insert, select

from serve_api import migrate
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
    assert ann.get("/follows").json()["counts"] == {"followers": 1, "following": 0, "friends": 0}


def test_removing_a_follower(app, ann, bob):
    befriend(ann, bob, "bob")
    assert bob.delete("/followers/ann").status_code == 204
    assert rel(bob, "ann") == "following"  # Bob still follows Ann
    assert names(bob.get("/follows").json()["followers"]) == []
    assert bob.delete("/followers/ann").status_code == 204  # already gone: fine


def test_follow_and_unfollow_are_idempotent(app, ann, bob):
    for _ in range(3):
        assert ann.put("/follows/bob").status_code == 200
    with db_of(app).engine.connect() as conn:
        assert len(conn.execute(select(follows)).all()) == 1
    assert bob.get("/follows").json()["counts"]["followers"] == 1
    for _ in range(2):
        assert ann.delete("/follows/bob").status_code == 204
    assert bob.get("/follows").json()["counts"]["followers"] == 0


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
    anonymous = person(app)
    res = anonymous.put("/follows/bob")
    assert res.status_code == 409 and "Choose a username first" in res.json()["detail"]


def test_lists_and_counts(app, ann, bob):
    carol, dave = person(app, "carol"), person(app, "dave")
    befriend(ann, bob, "bob")
    carol.put("/follows/ann")  # a follower
    ann.put("/follows/dave")  # following
    lists = ann.get("/follows").json()
    assert lists["counts"] == {"followers": 2, "following": 2, "friends": 1}
    assert names(lists["friends"]) == ["bob"]
    assert sorted(names(lists["followers"])) == ["bob", "carol"]
    assert sorted(names(lists["following"])) == ["bob", "dave"]
    carol_entry = next(e for e in lists["followers"] if e["person"]["username"] == "carol")
    assert carol_entry["follows_you"] is True and carol_entry["you_follow"] is False
    # Counts show on anyone's page.
    assert dave.get("/people/ann").json()["counts"] == {"followers": 2, "following": 2, "friends": 1}


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
    assert ann.get("/follows").json()["counts"] == {"followers": 0, "following": 0, "friends": 0}
    for res in (ann.get("/people/bob"), ann.put("/follows/bob"), ann.delete("/follows/bob")):
        assert res.status_code == 404 and res.json()["detail"] == "No one has that username."
    assert bob.get("/people/ann").status_code == 404
    bob.delete("/blocks/ann")
    assert rel(ann, "bob") == "none"  # unblocking doesn't bring the follows back


def test_suspended_accounts_leave_lists_and_counts(app, ann, bob):
    befriend(ann, bob, "bob")
    bob_id = bob.get("/auth/me").json()["id"]
    db_of(app).suspend(bob_id, "test")
    assert ann.get("/follows").json()["counts"] == {"followers": 0, "following": 0, "friends": 0}
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
    assert ann.get("/follows").json()["counts"] == {"followers": 0, "following": 0, "friends": 0}
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

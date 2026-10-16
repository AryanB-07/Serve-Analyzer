"""The feed: Public (everyone's public posts) and Friends (friends' posts), newest first, paged."""

import pytest
from fastapi.testclient import TestClient

from tests.test_account import app, client, db_of, mailer, signup  # noqa: F401
from tests.test_follows import befriend, person
from tests.test_posts import post


@pytest.fixture
def settings(tmp_path):  # no email verification, so analyses can be made straight away
    from serve_api.settings import Settings

    return Settings(data_dir=tmp_path, secret="test", public_base="", verify_email=False)


def feed(c: TestClient, tab: str, limit: int = 30) -> list[str]:
    """Every post id in a tab, walking the pages."""
    ids, cursor = [], None
    while True:
        res = c.get("/feed", params={"tab": tab, "limit": limit, **({"cursor": cursor} if cursor else {})})
        assert res.status_code == 200, res.text
        ids += [p["id"] for p in res.json()["items"]]
        if not (cursor := res.json()["next_cursor"]):
            return ids


@pytest.fixture
def world(app, settings):
    """Ann; Bob her friend; Carol, whom Ann follows one way; Dave, a stranger. Each posts twice."""
    ann, bob, carol, dave = (person(app, n) for n in ("ann", "bob", "carol", "dave"))
    befriend(ann, bob, "bob")
    ann.put("/follows/carol")
    made = {}
    for name, c in (("ann", ann), ("bob", bob), ("carol", carol), ("dave", dave)):
        made[name] = {v: post(app, settings, c, v)["id"] for v in ("public", "friends")}
    return {"ann": ann, "bob": bob, "carol": carol, "dave": dave, "posts": made}


def test_public_is_everyones_public_posts_newest_first(world):
    p = world["posts"]
    public = feed(world["ann"], "public")
    assert public == [p[n]["public"] for n in ("dave", "carol", "bob", "ann")]  # made in that order, oldest first
    assert not set(public) & {p[n]["friends"] for n in p}


def test_friends_is_friends_posts_of_both_kinds(world):
    p = world["posts"]
    friends = feed(world["ann"], "friends")
    assert friends == [p["bob"]["friends"], p["bob"]["public"]]
    # Not her own, not Carol (followed one way), not Dave (a stranger).
    assert feed(world["carol"], "friends") == []
    assert feed(world["bob"], "friends") == [p["ann"]["friends"], p["ann"]["public"]]


def test_ending_a_friendship_empties_the_friends_tab_at_once(world):
    world["ann"].delete("/follows/bob")
    assert feed(world["ann"], "friends") == []
    assert feed(world["bob"], "friends") == []


def test_hidden_people_are_left_out_of_both_tabs(app, world):
    p = world["posts"]
    world["dave"].post("/blocks", json={"username": "ann"})  # Dave blocks Ann
    assert p["dave"]["public"] not in feed(world["ann"], "public")
    assert p["ann"]["public"] not in feed(world["dave"], "public")
    db_of(app).suspend(world["bob"].get("/auth/me").json()["id"], "test")
    assert p["bob"]["public"] not in feed(world["ann"], "public")
    assert feed(world["ann"], "friends") == []


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_pages_have_no_repeats_or_gaps(world, limit):
    everything = feed(world["ann"], "public", 30)
    assert feed(world["ann"], "public", limit) == everything


def test_bad_requests(app, world):
    assert world["ann"].get("/feed", params={"tab": "everything"}).status_code == 422
    assert world["ann"].get("/feed", params={"limit": 31}).status_code == 422
    assert world["ann"].get("/feed", params={"cursor": "nonsense"}).status_code == 422
    assert TestClient(app).get("/feed").status_code == 401


def test_feed_posts_carry_counts_and_your_like(world):
    p = world["posts"]
    world["ann"].put(f"/posts/{p['dave']['public']}/like")
    item = next(x for x in world["ann"].get("/feed").json()["items"] if x["id"] == p["dave"]["public"])
    assert item["liked_by_you"] is True and item["like_count"] == 1 and item["author"]["username"] == "dave"

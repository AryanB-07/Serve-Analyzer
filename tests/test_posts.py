"""Posts: who can see them, likes, comments, editing and deleting, and their stored files."""

import uuid
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from serve_api import keys
from serve_api.storage import LocalStorage
from serve_api.tables import post_comments, post_likes, posts
from tests.test_account import PASSWORD, app, client, db_of, mailer, signup  # noqa: F401
from tests.test_follows import befriend, person
from tests.test_shared_serves import finished


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


def serve(app, settings, c: TestClient) -> str:
    """A finished analysis with its skeleton video too (what a post copies)."""
    analysis_id = finished(app, settings, c)
    LocalStorage(settings).path(keys.output_key(analysis_id, keys.ANNOTATED)).write_bytes(b"skeleton video")
    return analysis_id


def post(app, settings, c: TestClient, visibility: str | None = None, caption: str | None = "My serve") -> dict:
    body = {"analysis_id": serve(app, settings, c), "caption": caption}
    if visibility:
        body["visibility"] = visibility
    res = c.post("/posts", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def can_see(c: TestClient, post_id: str) -> bool:
    return c.get(f"/posts/{post_id}").status_code == 200


def fetch(c: TestClient, url: str):
    parts = urlsplit(url)
    return c.get(f"{parts.path}?{parts.query}")


# --- posting -------------------------------------------------------------------------------------

def test_a_post_is_a_snapshot_of_your_serve(app, settings, ann):
    created = post(app, settings, ann)
    assert created["visibility"] == "friends"  # the default
    assert created["caption"] == "My serve" and created["is_yours"] and created["author"]["username"] == "ann"
    assert created["overall_score"] == 77 and created["like_count"] == 0 and created["comment_count"] == 0
    assert fetch(ann, created["video_url"]).content == b"skeleton video"
    # Never the analysis's note or filename.
    text = ann.get(f"/posts/{created['id']}").text
    assert "secret-session" not in text and "my coach says" not in text


def test_only_your_own_finished_serves_can_be_posted(app, settings, ann, bob):
    theirs = serve(app, settings, bob)
    assert ann.post("/posts", json={"analysis_id": theirs}).status_code == 404
    failed = finished(app, settings, ann, status="failed")
    assert ann.post("/posts", json={"analysis_id": failed}).status_code == 404
    assert ann.post("/posts", json={"analysis_id": serve(app, settings, ann), "visibility": "everyone"}).status_code == 422
    assert ann.post("/posts", json={"analysis_id": serve(app, settings, ann), "caption": "x" * 501}).status_code == 422
    assert TestClient(app).post("/posts", json={"analysis_id": theirs}).status_code == 401


def test_deleting_the_analysis_doesnt_break_the_post(app, settings, ann):
    created = post(app, settings, ann)
    analysis_id = db_of(app).get_post(created["id"])["analysis_id"]
    assert ann.delete(f"/analyses/{analysis_id}").status_code == 204
    again = ann.get(f"/posts/{created['id']}").json()
    assert fetch(ann, again["video_url"]).status_code == 200


# --- who can see a post --------------------------------------------------------------------------

def test_a_friends_post_is_only_for_the_author_and_their_friends(app, settings, ann, bob):
    carol, dave, eve = person(app, "carol"), person(app, "dave"), person(app, "eve")
    befriend(ann, bob, "bob")
    carol.put("/follows/ann")  # follows Ann, not followed back
    ann.put("/follows/dave")  # Ann follows Dave, not followed back
    friends_only = post(app, settings, ann)
    assert can_see(ann, friends_only["id"]) and can_see(bob, friends_only["id"])
    for outsider in (carol, dave, eve):
        assert not can_see(outsider, friends_only["id"])
    assert TestClient(app).get(f"/posts/{friends_only['id']}").status_code == 401


def test_a_public_post_is_for_everyone_signed_in(app, settings, ann):
    public = post(app, settings, ann, "public")
    assert can_see(person(app, "stranger"), public["id"])
    assert TestClient(app).get(f"/posts/{public['id']}").status_code == 401  # not the open web


def test_ending_a_friendship_ends_access_at_once(app, settings, ann, bob):
    befriend(ann, bob, "bob")
    friends_only = post(app, settings, ann)
    assert can_see(bob, friends_only["id"])
    ann.delete("/followers/bob")  # Ann removes Bob as a follower: no longer friends
    assert not can_see(bob, friends_only["id"])
    for res in (bob.put(f"/posts/{friends_only['id']}/like"), bob.get(f"/posts/{friends_only['id']}/comments"),
                bob.post(f"/posts/{friends_only['id']}/comments", json={"body": "hi"})):
        assert res.status_code == 404


def test_blocks_and_suspensions_hide_even_public_posts(app, settings, ann, bob):
    public = post(app, settings, ann, "public")
    ann.post("/blocks", json={"username": "bob"})
    assert not can_see(bob, public["id"])
    ann.delete("/blocks/bob")
    db_of(app).suspend(ann.get("/auth/me").json()["id"], "test")
    assert not can_see(bob, public["id"])


def test_profiles_list_the_posts_you_can_see(app, settings, ann, bob):
    stranger = person(app, "stranger")
    befriend(ann, bob, "bob")
    public = post(app, settings, ann, "public")
    friends_only = post(app, settings, ann, "friends")
    ids = lambda c: [p["id"] for p in c.get("/people/ann/posts").json()["items"]]  # noqa: E731
    assert ids(ann) == [friends_only["id"], public["id"]]  # newest first
    assert ids(bob) == [friends_only["id"], public["id"]]
    assert ids(stranger) == [public["id"]]
    ann.post("/blocks", json={"username": "stranger"})
    assert stranger.get("/people/ann/posts").status_code == 404


def test_profile_posts_page(app, settings, ann):
    made = [post(app, settings, ann, "public")["id"] for _ in range(5)]
    seen, cursor = [], None
    while True:
        page = ann.get("/people/ann/posts", params={"limit": 2, **({"cursor": cursor} if cursor else {})}).json()
        seen += [p["id"] for p in page["items"]]
        if not (cursor := page["next_cursor"]):
            break
    assert seen == list(reversed(made))


def test_video_links_are_signed_and_stop_working(app, settings, ann, bob):
    befriend(ann, bob, "bob")
    created = post(app, settings, ann)
    url = urlsplit(created["video_url"])
    assert fetch(bob, created["video_url"]).status_code == 200
    # Tamper with the signature, or guess the path: refused.
    assert bob.get(f"{url.path}?{url.query[:-4]}abcd").status_code == 403
    assert bob.get(url.path).status_code == 422  # no signature at all
    # Deleted: the file is gone.
    ann.delete(f"/posts/{created['id']}")
    assert fetch(bob, created["video_url"]).status_code == 404


# --- your own content ----------------------------------------------------------------------------

def test_only_the_author_can_edit_or_delete(app, settings, ann, bob):
    befriend(ann, bob, "bob")
    created = post(app, settings, ann)
    assert bob.patch(f"/posts/{created['id']}", json={"caption": "hijacked"}).status_code == 404
    assert bob.delete(f"/posts/{created['id']}").status_code == 404
    edited = ann.patch(f"/posts/{created['id']}", json={"caption": "  New caption  ", "visibility": "public"})
    assert edited.status_code == 200 and edited.json()["caption"] == "New caption" and edited.json()["visibility"] == "public"
    assert ann.patch(f"/posts/{created['id']}", json={"caption": ""}).json()["caption"] is None
    assert ann.patch(f"/posts/{created['id']}", json={"visibility": None}).status_code == 422


def test_deleting_a_post_removes_its_likes_comments_and_files(app, settings, ann, bob):
    befriend(ann, bob, "bob")
    created = post(app, settings, ann)
    bob.put(f"/posts/{created['id']}/like")
    bob.post(f"/posts/{created['id']}/comments", json={"body": "Nice"})
    folder = settings.data_dir / "objects" / keys.post_prefix(created["id"])
    assert folder.exists()
    assert ann.delete(f"/posts/{created['id']}").status_code == 204
    assert not folder.exists()
    with db_of(app).engine.connect() as conn:
        for table in (posts, post_likes, post_comments):
            assert conn.execute(select(func.count()).select_from(table)).scalar_one() == 0
    assert ann.delete(f"/posts/{created['id']}").status_code == 404


# --- likes ---------------------------------------------------------------------------------------

def test_likes_are_one_per_person_and_idempotent(app, settings, ann, bob):
    befriend(ann, bob, "bob")
    created = post(app, settings, ann)
    for _ in range(3):
        assert bob.put(f"/posts/{created['id']}/like").json() == {"liked": True, "like_count": 1}
    assert ann.put(f"/posts/{created['id']}/like").json() == {"liked": True, "like_count": 2}
    seen = bob.get(f"/posts/{created['id']}").json()
    assert seen["like_count"] == 2 and seen["liked_by_you"] is True
    for _ in range(2):
        assert bob.delete(f"/posts/{created['id']}/like").json() == {"liked": False, "like_count": 1}


# --- comments ------------------------------------------------------------------------------------

def test_comments_come_in_order_and_page(app, settings, ann, bob):
    befriend(ann, bob, "bob")
    created = post(app, settings, ann)
    for i in range(5):
        (ann if i % 2 else bob).post(f"/posts/{created['id']}/comments", json={"body": f"c{i}"})
    first = ann.get(f"/posts/{created['id']}/comments", params={"limit": 3}).json()
    assert [c["body"] for c in first["items"]] == ["c0", "c1", "c2"]
    rest = ann.get(f"/posts/{created['id']}/comments", params={"cursor": first["next_cursor"]}).json()
    assert [c["body"] for c in rest["items"]] == ["c3", "c4"] and rest["next_cursor"] is None
    assert ann.get(f"/posts/{created['id']}").json()["comment_count"] == 5


def test_comments_can_be_deleted_by_their_author_or_the_posts_author(app, settings, ann, bob):
    carol = person(app, "carol")
    for other, name in ((bob, "bob"), (carol, "carol")):
        befriend(ann, other, name)
    created = post(app, settings, ann)
    bobs = bob.post(f"/posts/{created['id']}/comments", json={"body": "From Bob"}).json()
    carols = carol.post(f"/posts/{created['id']}/comments", json={"body": "From Carol"}).json()
    assert bobs["can_delete"] is True
    seen_by_carol = {c["body"]: c["can_delete"] for c in carol.get(f"/posts/{created['id']}/comments").json()["items"]}
    assert seen_by_carol == {"From Bob": False, "From Carol": True}
    assert carol.delete(f"/comments/{bobs['id']}").status_code == 404  # not hers
    assert bob.delete(f"/comments/{bobs['id']}").status_code == 204  # his own
    assert ann.delete(f"/comments/{carols['id']}").status_code == 204  # on her post
    assert ann.get(f"/posts/{created['id']}/comments").json()["items"] == []


def test_comments_are_checked(app, settings, ann):
    created = post(app, settings, ann)
    url = f"/posts/{created['id']}/comments"
    assert ann.post(url, json={"body": "   "}).status_code == 422
    assert ann.post(url, json={"body": "x" * 1001}).status_code == 422
    assert ann.post(url, json={"body": "line one\r\nline two\x07"}).json()["body"] == "line one\nline two"


def test_comments_from_people_hidden_from_you_are_left_out(app, settings, ann, bob):
    carol = person(app, "carol")
    public = post(app, settings, ann, "public")
    carol.post(f"/posts/{public['id']}/comments", json={"body": "Carol here"})
    carol.post("/blocks", json={"username": "bob"})
    assert bob.get(f"/posts/{public['id']}/comments").json()["items"] == []
    assert [c["body"] for c in ann.get(f"/posts/{public['id']}/comments").json()["items"]] == ["Carol here"]


# --- reports, deletion and the data download -----------------------------------------------------

def test_posts_and_comments_can_be_reported(app, settings, ann, bob):
    public = post(app, settings, ann, "public", caption="Buy my course")
    comment = ann.post(f"/posts/{public['id']}/comments", json={"body": "spammy"}).json()
    assert bob.post("/reports", json={"username": "ann", "post_id": public["id"], "reason": "spam"}).status_code == 201
    assert bob.post("/reports", json={"username": "ann", "comment_id": comment["id"], "reason": "spam"}).status_code == 201
    copies = [r["message_body"] for r in db_of(app).people_reports()]
    assert copies == ["Buy my course", "spammy"]
    friends_only = post(app, settings, ann)
    assert bob.post("/reports", json={"username": "ann", "post_id": friends_only["id"], "reason": "spam"}).status_code == 404


def test_deleting_an_account_removes_its_posts_likes_and_comments(app, settings, ann, bob):
    public = post(app, settings, ann, "public")
    bobs_post = post(app, settings, bob, "public")
    ann.put(f"/posts/{bobs_post['id']}/like")
    ann.post(f"/posts/{bobs_post['id']}/comments", json={"body": "from ann"})
    folder = settings.data_dir / "objects" / keys.post_prefix(public["id"])
    assert ann.request("DELETE", "/auth/me", json={"password": PASSWORD}).status_code == 204
    assert not folder.exists()
    seen = bob.get(f"/posts/{bobs_post['id']}").json()
    assert seen["like_count"] == 0 and seen["comment_count"] == 0
    assert not can_see(bob, public["id"])


def test_the_data_download_has_posts_comments_and_likes(app, settings, ann, bob):
    mine = post(app, settings, ann, "public", caption="Mine")
    theirs = post(app, settings, bob, "public")
    ann.put(f"/posts/{theirs['id']}/like")
    ann.post(f"/posts/{theirs['id']}/comments", json={"body": "Great toss"})
    data = ann.get("/auth/me/export").json()
    assert [(p["id"], p["caption"], p["visibility"]) for p in data["posts"]] == [(mine["id"], "Mine", "public")]
    assert set(data["posts"][0]["files"]) == {"video", "thumbnail"}
    assert data["comments"] == [{"post_id": theirs["id"], "body": "Great toss", "created_at": data["comments"][0]["created_at"]}]
    assert data["likes"] == [theirs["id"]]


def test_posting_is_rate_limited(app, settings, ann):
    db = db_of(app)
    user_id = ann.get("/auth/me").json()["id"]
    from serve_api.db import now
    for _ in range(20):
        db.create_post({"id": uuid.uuid4().hex, "user_id": user_id, "analysis_id": None, "caption": None,
                        "visibility": "friends", "hand": "right", "overall_score": None, "key_scores": None,
                        "recorded_at": now(), "created_at": now(), "updated_at": now()})
    assert ann.post("/posts", json={"analysis_id": serve(app, settings, ann)}).status_code == 429

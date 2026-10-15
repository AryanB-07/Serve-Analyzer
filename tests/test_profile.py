"""Profiles (username, display name, bio, picture, stats) and changing the password in Settings."""

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from serve_api import keys
from serve_api.avatars import clean, jpeg_size
from serve_api.tables import analyses, sessions
from tests.test_account import (  # noqa: F401
    NEW_PASSWORD,
    PASSWORD,
    app,
    client,
    create_analysis,
    db_of,
    mailer,
    settings,
    signup,
    verify,
)


def jpeg(width=512, height=512, colour=(40, 120, 200), exif: bytes | None = None) -> bytes:
    image = np.zeros((height, width, 3), np.uint8)
    image[:] = colour
    data = cv2.imencode(".jpg", image)[1].tobytes()
    if exif is not None:  # an APP1 segment straight after the start-of-image marker
        segment = b"Exif\x00\x00" + exif
        data = data[:2] + b"\xff\xe1" + (len(segment) + 2).to_bytes(2, "big") + segment + data[2:]
    return data


def put_avatar(client, data: bytes, content_type="image/jpeg"):
    return client.put("/profile/avatar", content=data, headers={"content-type": content_type})


@pytest.fixture
def me(client, mailer):
    verify(client, mailer, signup(client))
    return client


def stranger(app) -> TestClient:
    other = TestClient(app)
    signup(other)
    return other


# --- the profile ---------------------------------------------------------------------------------

def test_a_new_account_has_its_username_and_nothing_else(me):
    profile = me.get("/profile").json()
    assert profile["username"].startswith("u")  # chosen at signup (tests/test_account.signup)
    assert profile["display_name"] is None and profile["bio"] is None
    assert profile["avatar_url"] is None and profile["member_since"]
    assert profile["stats"] == {"serves": 0, "average_score": None, "averaged_over": 0, "best_score": None}


def test_profile_fields_are_cleaned_and_saved(me):
    res = me.patch("/profile", json={"username": " @Ace_Server ", "display_name": "  Aryan \t B ",
                                     "bio": "  Lefty.\r\nWorking on my kick serve.  "})
    assert res.status_code == 200, res.text
    assert {k: res.json()[k] for k in ("username", "display_name", "bio")} == {
        "username": "ace_server", "display_name": "Aryan B", "bio": "Lefty.\nWorking on my kick serve."}
    # Only the fields sent change; an empty one is removed.
    res = me.patch("/profile", json={"bio": "   "})
    assert res.json()["bio"] is None and res.json()["username"] == "ace_server"
    assert me.get("/profile").json()["display_name"] == "Aryan B"


@pytest.mark.parametrize("username, problem", [
    ("ab", "3 to 20"), ("a" * 21, "3 to 20"), ("has space", "letters, numbers"), ("dash-ed", "letters, numbers"),
    ("émile", "letters, numbers"), ("admin", "reserved"), ("Support", "reserved"),
])
def test_usernames_follow_the_rules(me, username, problem):
    res = me.patch("/profile", json={"username": username})
    assert res.status_code == 422 and problem in res.text
    check = me.get("/profile/username-check", params={"username": username}).json()
    assert check["available"] is False and problem in check["problem"]


def test_a_username_can_be_changed_but_not_removed(me):
    me.patch("/profile", json={"username": "first_name"})
    assert me.patch("/profile", json={"username": None}).status_code == 422
    assert me.patch("/profile", json={"username": "second_name"}).json()["username"] == "second_name"


def test_usernames_are_unique_ignoring_case(app, me):
    me.patch("/profile", json={"username": "ace"})
    other = stranger(app)
    res = other.patch("/profile", json={"username": "ACE"})
    assert res.status_code == 409 and res.json()["detail"] == "That username is taken."
    assert other.get("/profile/username-check", params={"username": "Ace"}).json() == {
        "username": "ace", "available": False, "problem": "That username is taken."}
    # Your own username counts as available to you; a free one is available to anyone.
    assert me.get("/profile/username-check", params={"username": "ace"}).json()["available"] is True
    assert other.get("/profile/username-check", params={"username": "ace2"}).json()["available"] is True
    # Once given up, it's held for its owner for a while (tests/test_moderation.py), not free.
    me.patch("/profile", json={"username": "renamed"})
    assert other.patch("/profile", json={"username": "ace"}).status_code == 409


def test_long_names_and_bios_are_refused(me):
    assert me.patch("/profile", json={"display_name": "x" * 51}).status_code == 422
    assert me.patch("/profile", json={"bio": "x" * 301}).status_code == 422
    assert me.patch("/profile", json={"display_name": "x" * 50, "bio": "y" * 300}).status_code == 200


def test_profiles_need_signing_in_and_are_your_own(app, me):
    me.patch("/profile", json={"username": "mine", "bio": "private for now"})
    assert TestClient(app).get("/profile").status_code == 401
    assert TestClient(app).patch("/profile", json={"bio": "x"}).status_code == 401
    other = stranger(app).get("/profile").json()
    assert other["username"] != "mine" and other["bio"] is None


def test_stats_count_finished_serves_and_average_the_latest_ten(app, me):
    db = db_of(app)
    scores = [50, 60, 70, None, 81, 90, 91, 92, 93, 94, 95, 96, 30]  # oldest first; one unscored
    for i, score in enumerate(scores):
        analysis_id = create_analysis(me).json()["analysis"]["id"]
        with db.engine.begin() as conn:
            conn.execute(update(analyses).where(analyses.c.id == analysis_id).values(
                status="succeeded", overall_score=score))
    failed = create_analysis(me).json()["analysis"]["id"]
    db.set_status(failed, "failed", error_code="NOT_A_SERVE", error_message="")
    stats = me.get("/profile").json()["stats"]
    latest = [s for s in scores if s is not None][-10:]
    assert stats["serves"] == len(scores)
    assert stats["best_score"] == 96 and stats["averaged_over"] == 10
    assert stats["average_score"] == int(sum(latest) / 10 + 0.5)


# --- the picture ---------------------------------------------------------------------------------

def test_a_square_picture_is_stored(app, settings, me):
    sent = jpeg(512, 512)
    res = put_avatar(me, sent)
    assert res.status_code == 200, res.text
    stored = me.get(res.json()["avatar_url"].removeprefix(settings.public_base))
    assert stored.status_code == 200 and stored.headers["content-type"] == "image/jpeg"
    assert stored.content == clean(sent) and jpeg_size(stored.content) == (512, 512)


def test_a_pictures_metadata_is_removed_and_it_still_decodes():
    with_gps = jpeg(exif=b"GPS 51.5007 N 0.1246 W secret-location")
    assert b"secret-location" in with_gps
    cleaned = clean(with_gps)
    assert b"secret-location" not in cleaned and b"Exif" not in cleaned
    decoded = cv2.imdecode(np.frombuffer(cleaned, np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None and decoded.shape == (512, 512, 3)
    assert abs(int(decoded[256, 256, 0]) - 40) < 8  # the same picture


def test_a_comment_segment_is_removed_too():
    data = jpeg()
    with_comment = data[:2] + b"\xff\xfe" + (len(b"made with SecretCam") + 2).to_bytes(2, "big") + b"made with SecretCam" + data[2:]
    assert b"SecretCam" not in clean(with_comment)


@pytest.mark.parametrize("data, content_type, code, detail", [
    (cv2.imencode(".png", np.zeros((100, 100, 3), np.uint8))[1].tobytes(), "image/jpeg", 422, "JPEG"),
    (b"\xff\xd8" + b"garbage" * 40, "image/jpeg", 422, "couldn't be read"),
    (jpeg(40, 40), "image/jpeg", 422, "at least 64"),
    (jpeg(900, 600), "image/jpeg", 422, "square"),
    (jpeg()[:-300], "image/jpeg", 422, "incomplete"),
    (jpeg(), "image/png", 415, "JPEG"),
])
def test_bad_pictures_are_refused(me, data, content_type, code, detail):
    res = put_avatar(me, data, content_type)
    assert res.status_code == code and detail in res.json()["detail"]
    assert me.get("/profile").json()["avatar_url"] is None


def test_a_huge_image_is_refused_from_its_header(me):
    # A valid header claiming 20000 x 20000 pixels: a browser decoding it would need over a gigabyte.
    header = jpeg(64, 64)
    sof = header.index(b"\xff\xc0")
    lying = header[:sof + 5] + (20000).to_bytes(2, "big") + (20000).to_bytes(2, "big") + header[sof + 9:]
    res = put_avatar(me, lying)
    assert res.status_code == 422 and "1024" in res.json()["detail"]


def test_an_oversized_upload_is_refused(me):
    res = put_avatar(me, b"\xff\xd8" + b"\x00" * (1024 * 1024 + 10))
    assert res.status_code == 413


def test_replacing_or_removing_a_picture_deletes_the_old_file(app, settings, me):
    storage_root = settings.data_dir / "objects"
    put_avatar(me, jpeg(colour=(0, 0, 255)))
    first = db_of(app).get_profile(me.get("/auth/me").json()["id"])["avatar_key"]
    put_avatar(me, jpeg(colour=(0, 255, 0)))
    second = db_of(app).get_profile(me.get("/auth/me").json()["id"])["avatar_key"]
    assert first != second
    assert not (storage_root / first).exists() and (storage_root / second).exists()
    res = me.delete("/profile/avatar")
    assert res.json()["avatar_url"] is None and not (storage_root / second).exists()


def test_pictures_are_rate_limited(me):
    for _ in range(20):
        assert put_avatar(me, jpeg(64, 64)).status_code == 200
    assert put_avatar(me, jpeg(64, 64)).status_code == 429


def test_the_profile_is_in_the_data_download_and_deleted_with_the_account(app, settings, me):
    me.patch("/profile", json={"username": "leaving", "display_name": "Soon Gone", "bio": "bye"})
    put_avatar(me, jpeg())
    exported = me.get("/auth/me/export").json()["profile"]
    assert {k: exported[k] for k in ("username", "display_name", "bio")} == {
        "username": "leaving", "display_name": "Soon Gone", "bio": "bye"}
    assert exported["avatar"]
    user_id = me.get("/auth/me").json()["id"]
    assert (settings.data_dir / "objects" / keys.avatar_prefix(user_id)).exists()
    assert me.request("DELETE", "/auth/me", json={"password": PASSWORD}).status_code == 204
    assert db_of(app).get_profile(user_id) is None
    assert not (settings.data_dir / "objects" / keys.avatar_prefix(user_id)).exists()
    # The username is held, so nobody can take it to pose as them (tests/test_moderation.py).
    assert stranger(app).patch("/profile", json={"username": "leaving"}).status_code == 409


# --- changing the password -----------------------------------------------------------------------

def test_changing_the_password_keeps_this_device_and_signs_out_the_rest(app, client, mailer):
    email = signup(client)
    other_device = TestClient(app)
    assert other_device.post("/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
    res = client.post("/auth/password-change", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert res.status_code == 204
    assert client.get("/auth/me").status_code == 200
    assert other_device.get("/auth/me").status_code == 401
    with db_of(app).engine.connect() as conn:
        assert len(conn.execute(select(sessions)).all()) == 1
    assert "every other device was signed out" in mailer.sent[-1].text
    # The new password works, the old one doesn't.
    fresh = TestClient(app)
    assert fresh.post("/auth/login", json={"email": email, "password": PASSWORD}).status_code == 401
    assert fresh.post("/auth/login", json={"email": email, "password": NEW_PASSWORD}).status_code == 200


def test_changing_the_password_needs_the_current_one(client):
    signup(client)
    res = client.post("/auth/password-change", json={"current_password": "wrong", "new_password": NEW_PASSWORD})
    assert res.status_code == 403
    short = client.post("/auth/password-change", json={"current_password": PASSWORD, "new_password": "short"})
    assert short.status_code == 422
    assert TestClient(client.app).post("/auth/password-change", json={
        "current_password": PASSWORD, "new_password": NEW_PASSWORD}).status_code == 401


def test_wrong_current_passwords_are_rate_limited(client):
    signup(client)
    for _ in range(10):
        client.post("/auth/password-change", json={"current_password": "wrong", "new_password": NEW_PASSWORD})
    res = client.post("/auth/password-change", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert res.status_code == 429


def test_changing_the_password_voids_reset_links(app, client, mailer):
    email = signup(client)
    client.post("/auth/password-reset", json={"email": email})
    link = mailer.last_link(email)
    client.post("/auth/password-change", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    token = link.split("token=")[1]
    res = TestClient(app).post("/auth/password-reset/confirm", json={"token": token, "password": "yet another one"})
    assert res.status_code == 400

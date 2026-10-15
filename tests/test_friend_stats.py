"""What friends see of each other's serves, and the friends leaderboard."""

from datetime import timedelta

import pytest
from sqlalchemy import update

from serve_api.db import now
from serve_api.tables import analyses
from tests.test_account import app, client, create_analysis, db_of, mailer, settings, signup  # noqa: F401
from tests.test_follows import befriend, person


def serves(app, client, scores, *, days_ago=None, positions=None):
    """Finished, scored analyses for ``client``'s account, oldest first."""
    db = db_of(app)
    for i, score in enumerate(scores):
        analysis_id = create_analysis(client).json()["analysis"]["id"]
        age = (days_ago[i] if days_ago else len(scores) - i) * timedelta(hours=1 if days_ago is None else 24)
        key = {"trunk_tilt": {"phase": "trophy", "value": 25.0, "score": positions[i], "band": "good"}} if positions else {}
        with db.engine.begin() as conn:
            conn.execute(update(analyses).where(analyses.c.id == analysis_id).values(
                status="succeeded", overall_score=score, key_scores=key, created_at=now() - age))


@pytest.fixture
def ann(app):
    return person(app, "ann")


@pytest.fixture
def bob(app):
    return person(app, "bob")


@pytest.fixture
def settings(tmp_path):  # noqa: F811  (no email verification, so analyses can be made straight away)
    from serve_api.settings import Settings

    return Settings(data_dir=tmp_path, secret="test", public_base="", verify_email=False)


# --- what friends see ----------------------------------------------------------------------------

def test_nothing_is_shared_until_you_turn_it_on(app, ann, bob):
    befriend(ann, bob, "bob")
    serves(app, bob, [70, 80])
    seen = ann.get("/people/bob").json()
    assert seen["stats"] is None and seen["positions"] is None
    profile = bob.get("/profile").json()
    assert (profile["share_stats"], profile["share_positions"], profile["on_leaderboard"]) == (False, False, False)


def test_a_friend_sees_shared_stats_with_a_trend(app, ann, bob):
    befriend(ann, bob, "bob")
    scores = [40, 45, 50, 55, 60, 70, 72, 74, 76, 78, 80, 90]
    serves(app, bob, scores)
    bob.patch("/profile", json={"share_stats": True})
    stats = ann.get("/people/bob").json()["stats"]
    latest = scores[-10:]
    assert stats["serves"] == 12 and stats["best_score"] == 90 and stats["averaged_over"] == 10
    assert stats["average_score"] == int(sum(latest) / 10 + 0.5)
    assert [p["score"] for p in stats["trend"]] == scores  # oldest first
    newest5, previous5 = scores[-5:], scores[-10:-5]
    assert stats["change"] == int(sum(newest5) / 5 + 0.5) - int(sum(previous5) / 5 + 0.5)
    assert ann.get("/people/bob").json()["positions"] is None  # not shared


def test_position_averages_are_shared_separately(app, ann, bob):
    befriend(ann, bob, "bob")
    serves(app, bob, [60, 70, 80], positions=[50, 60, 100])
    bob.patch("/profile", json={"share_positions": True})
    seen = ann.get("/people/bob").json()
    assert seen["stats"] is None
    assert seen["positions"]["trunk_tilt"] == {"score": 70, "measured": 3}
    assert seen["positions"]["elbow_angle"] is None  # never measured


def test_turning_sharing_off_hides_it_at_once(app, ann, bob):
    befriend(ann, bob, "bob")
    serves(app, bob, [70])
    bob.patch("/profile", json={"share_stats": True, "share_positions": True})
    assert ann.get("/people/bob").json()["stats"] is not None
    bob.patch("/profile", json={"share_stats": False, "share_positions": False})
    seen = ann.get("/people/bob").json()
    assert seen["stats"] is None and seen["positions"] is None


def test_strangers_and_ex_friends_see_no_stats(app, ann, bob):
    serves(app, bob, [70])
    bob.patch("/profile", json={"share_stats": True, "share_positions": True})
    assert ann.get("/people/bob").json()["stats"] is None  # not friends
    befriend(ann, bob, "bob")
    assert ann.get("/people/bob").json()["stats"] is not None
    ann.delete("/follows/bob")  # unfollowing ends the friendship
    assert ann.get("/people/bob").json()["stats"] is None


def test_no_scores_means_empty_stats_not_an_error(app, ann, bob):
    befriend(ann, bob, "bob")
    bob.patch("/profile", json={"share_stats": True, "share_positions": True})
    seen = ann.get("/people/bob").json()
    assert seen["stats"] == {"serves": 0, "average_score": None, "averaged_over": 0, "best_score": None,
                             "trend": [], "change": None}
    assert all(v is None for v in seen["positions"].values())


def test_sharing_switches_are_on_or_off(bob):
    for field in ("share_stats", "share_positions", "on_leaderboard"):
        assert bob.patch("/profile", json={field: None}).status_code == 422


# --- the leaderboard -----------------------------------------------------------------------------

def test_the_leaderboard_ranks_friends_who_joined_it(app, ann, bob):
    carol, dave = person(app, "carol"), person(app, "dave")
    for other, name in ((bob, "bob"), (carol, "carol"), (dave, "dave")):
        befriend(ann, other, name)
    serves(app, ann, [60] * 5)
    serves(app, bob, [80] * 5)
    serves(app, carol, [70] * 5)
    serves(app, dave, [95] * 5)  # hasn't joined
    for c in (ann, bob, carol):
        c.patch("/profile", json={"on_leaderboard": True})
    board = ann.get("/leaderboard").json()
    assert (board["window_days"], board["min_serves"], board["averaged_over"]) == (90, 5, 10)
    assert board["you_are_on_it"] is True
    assert [(e["rank"], e["person"]["username"], e["average_score"], e["is_you"]) for e in board["ranked"]] == [
        (1, "bob", 80, False), (2, "carol", 70, False), (3, "ann", 60, True)]
    assert board["not_ranked"] == []


def test_too_few_serves_in_the_window_means_not_ranked(app, ann, bob):
    befriend(ann, bob, "bob")
    serves(app, bob, [90, 90, 90, 90, 90, 90], days_ago=[200, 120, 30, 20, 10, 1])  # 4 in the last 90 days
    bob.patch("/profile", json={"on_leaderboard": True})
    board = ann.get("/leaderboard").json()
    assert board["ranked"] == [] and board["you_are_on_it"] is False
    entry = board["not_ranked"][0]
    assert entry["person"]["username"] == "bob" and entry["scored_serves"] == 4 and entry["needed"] == 1
    assert entry["average_score"] is None and entry["rank"] is None


def test_ties_share_a_rank(app, ann, bob):
    carol = person(app, "carol")
    befriend(ann, bob, "bob")
    befriend(ann, carol, "carol")
    serves(app, ann, [70] * 5)
    serves(app, bob, [80] * 5)
    serves(app, carol, [80] * 6)
    for c in (ann, bob, carol):
        c.patch("/profile", json={"on_leaderboard": True})
    ranks = [(e["rank"], e["person"]["username"]) for e in ann.get("/leaderboard").json()["ranked"]]
    assert ranks == [(1, "carol"), (1, "bob"), (3, "ann")]  # carol first: more serves


def test_the_leaderboard_never_includes_strangers(app, ann, bob):
    stranger = person(app, "stranger")
    serves(app, stranger, [99] * 5)
    stranger.patch("/profile", json={"on_leaderboard": True})
    befriend(ann, bob, "bob")
    assert ann.get("/leaderboard").json()["ranked"] == []
    assert ann.get("/leaderboard").json()["not_ranked"] == []


def test_sharing_settings_are_in_the_data_download(bob):
    bob.patch("/profile", json={"share_stats": True, "on_leaderboard": True})
    profile = bob.get("/auth/me/export").json()["profile"]
    assert (profile["share_stats"], profile["share_positions"], profile["on_leaderboard"]) == (True, False, True)

"""Following, friends (people who follow each other) and blocks.

Following is one-way and needs no approval, unless someone turns "let people follow me" off.
Two people are friends when each follows the other; friendship is worked out from the follows,
never stored. Unfollowing a friend ends the friendship. You can also remove a follower.

Someone who isn't your friend sees your display name, username, picture and follow counts; a
friend also sees your bio, and whatever serve stats you share. A block removes the follows
both ways and hides each person from the other completely: to the blocked person, the blocker
simply doesn't exist (404, the same as a username nobody has), so a block can't be detected.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status

from .auth import Auth, RateLimiter, _too_many
from .db import Database, now
from .schemas import (
    BlockedPerson,
    ErrorResponse,
    FollowCounts,
    FollowEntry,
    FollowLists,
    Leaderboard,
    LeaderboardEntry,
    Person,
    PersonSummary,
    SharedStats,
    User,
    UsernameRequest,
    normalise_username,
)
from .storage import Storage

NOT_FOUND = "No one has that username."
# The leaderboard: the average of each person's latest serves within the window, ranked once
# they have enough of them.
LEADERBOARD_DAYS = 90
LEADERBOARD_MIN = 5
LEADERBOARD_AVERAGED = 10
NEED_USERNAME = "Choose a username first, so people can see who's following them. You can set one in Settings."
NOT_ALLOWED = "They aren't accepting new followers."


def social_router(db: Database, storage: Storage, auth: Auth) -> APIRouter:
    router = APIRouter(tags=["friends"])
    signed_in = Depends(auth.current_user)
    new_follows = RateLimiter(db, "follow", limit=60, window=timedelta(hours=1))
    lookups = RateLimiter(db, "person-lookup", limit=120, window=timedelta(minutes=10))
    errors = {401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}

    def summary(profile: dict | None) -> PersonSummary:
        profile = profile or {}
        avatar = profile.get("avatar_key")
        return PersonSummary(username=profile.get("username"), display_name=profile.get("display_name"),
                             avatar_url=storage.presign("GET", avatar)[0] if avatar else None)

    def visible(username: str, user: User) -> dict:
        """The person with ``username``, unless there's none or they're hidden (a block either way,
        or a suspension). Both are 404."""
        person = db.person_by_username(normalise_username(username)[:40])
        if person is None or (person["user_id"] != user.id and db.hidden_between(user.id, person["user_id"])):
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
        return person

    def relationship(user_id: str, other_id: str) -> str:
        you_follow = db.follow_row(user_id, other_id) is not None
        follows_you = db.follow_row(other_id, user_id) is not None
        return {(True, True): "friends", (True, False): "following", (False, True): "follows_you"}.get(
            (you_follow, follows_you), "none")

    def person_view(person: dict, user: User) -> Person:
        counts = FollowCounts(**db.follow_counts(person["user_id"]))
        if person["user_id"] == user.id:
            return Person(**summary(person).model_dump(), relationship="self", counts=counts, bio=person["bio"])
        rel = relationship(user.id, person["user_id"])
        friends = rel == "friends"
        shared = db.serve_summary(person["user_id"]) if friends and (person["share_stats"] or person["share_positions"]) else None
        return Person(
            **summary(person).model_dump(), relationship=rel, counts=counts,
            can_follow=rel in ("none", "follows_you") and (bool(person["allow_follows"]) or rel == "follows_you"),
            bio=person["bio"] if friends else None,
            friends_since=db.friends_since(user.id, person["user_id"]) if friends else None,
            # Read when asked, so turning a setting off hides it at once.
            stats=SharedStats(**shared) if shared and person["share_stats"] else None,
            positions=shared["positions"] if shared and person["share_positions"] else None,
        )

    def limited(limiter: RateLimiter, user: User) -> None:
        if wait := limiter.retry_after(user.id):
            raise _too_many(wait)
        limiter.hit(user.id)

    @router.get("/people/{username}", response_model=Person, responses={**errors, 429: {"model": ErrorResponse}})
    def get_person(username: str, user: User = signed_in) -> Person:
        """Someone's page: what they show you, and where the two of you stand."""
        limited(lookups, user)
        return person_view(visible(username, user), user)

    @router.get("/follows", response_model=FollowLists, responses=errors)
    def my_lists(user: User = signed_in) -> FollowLists:
        """Your friends, followers and following, newest first."""
        lists = db.follow_lists(user.id)
        followers = {f["user_id"] for f in lists["followers"]}
        following = {f["user_id"] for f in lists["following"]}
        profiles = db.profiles_of(list(followers | following))
        entry = lambda f: FollowEntry(person=summary(profiles.get(f["user_id"])), since=f["since"],  # noqa: E731
                                      you_follow=f["user_id"] in following, follows_you=f["user_id"] in followers)
        return FollowLists(counts=FollowCounts(**{k: len(v) for k, v in lists.items()}),
                           **{k: [entry(f) for f in v] for k, v in lists.items()})

    @router.put("/follows/{username}", response_model=Person,
                responses={**errors, 400: {"model": ErrorResponse}, 403: {"model": ErrorResponse},
                           409: {"model": ErrorResponse}, 429: {"model": ErrorResponse}})
    def follow(username: str, user: User = signed_in) -> Person:
        """Follow someone (or follow them back). Doing it again changes nothing."""
        person = visible(username, user)
        if person["user_id"] == user.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't follow yourself.")
        if db.follow_row(user.id, person["user_id"]):
            return person_view(person, user)  # already following: a double tap
        if not (db.get_profile(user.id) or {}).get("username"):
            raise HTTPException(status.HTTP_409_CONFLICT, NEED_USERNAME)
        follows_you = db.follow_row(person["user_id"], user.id) is not None
        if not person["allow_follows"] and not follows_you:
            raise HTTPException(status.HTTP_403_FORBIDDEN, NOT_ALLOWED)
        limited(new_follows, user)
        if db.follow(user.id, person["user_id"]):
            # One notification per follow: an unfollow and follow again doesn't pile them up.
            db.forget_notifications_between(user.id, person["user_id"], ("new_follower", "followed_back"))
            db.notify(person["user_id"], "followed_back" if follows_you else "new_follower", user.id)
        return person_view(person, user)

    @router.delete("/follows/{username}", status_code=204, responses=errors)
    def unfollow(username: str, user: User = signed_in) -> Response:
        """Stop following someone; if you were friends, you aren't any more. Already not
        following is fine."""
        person = visible(username, user)
        if db.unfollow(user.id, person["user_id"]):
            db.forget_notifications_between(user.id, person["user_id"], ("new_follower", "followed_back"))
        return Response(status_code=204)

    @router.delete("/followers/{username}", status_code=204, responses=errors)
    def remove_follower(username: str, user: User = signed_in) -> Response:
        """Remove someone from your followers (they aren't told). Ends a friendship too."""
        person = visible(username, user)
        if db.unfollow(person["user_id"], user.id):
            db.forget_notifications_between(user.id, person["user_id"], ("new_follower", "followed_back"))
        return Response(status_code=204)

    @router.get("/leaderboard", response_model=Leaderboard, responses=errors)
    def leaderboard(user: User = signed_in) -> Leaderboard:
        """You and your friends who chose to be on it, ranked by the average of each one's latest
        serves in the window. Too few serves in the window means not ranked yet."""
        me = db.get_profile(user.id) or {}
        people = [uid for uid, p in db.profiles_of(db.friend_ids(user.id)).items() if p["on_leaderboard"]]
        if me.get("on_leaderboard"):
            people.append(user.id)
        profiles = {**db.profiles_of(people), **({user.id: me} if me else {})}
        numbers = db.leaderboard_numbers(people, now() - timedelta(days=LEADERBOARD_DAYS), LEADERBOARD_AVERAGED)
        entries = [LeaderboardEntry(
            person=summary(profiles.get(uid)), is_you=uid == user.id, average_score=n["average"],
            scored_serves=n["scored"], needed=max(0, LEADERBOARD_MIN - n["scored"]),
        ) for uid, n in numbers.items()]
        ranked = sorted((e for e in entries if e.needed == 0),
                        key=lambda e: (-(e.average_score or 0), -e.scored_serves, e.person.username or ""))
        for i, entry in enumerate(ranked):  # ties share a rank: 1, 1, 3
            same = i > 0 and entry.average_score == ranked[i - 1].average_score
            entry.rank = ranked[i - 1].rank if same else i + 1
        not_ranked = sorted((e for e in entries if e.needed), key=lambda e: (e.needed, e.person.username or ""))
        for entry in not_ranked:
            entry.average_score = None  # an average of one or two serves would mislead
        return Leaderboard(window_days=LEADERBOARD_DAYS, min_serves=LEADERBOARD_MIN, averaged_over=LEADERBOARD_AVERAGED,
                           you_are_on_it=bool(me.get("on_leaderboard")), ranked=ranked, not_ranked=not_ranked)

    @router.get("/blocks", response_model=list[BlockedPerson], responses=errors)
    def list_blocks(user: User = signed_in) -> list[BlockedPerson]:
        rows = db.blocked_by(user.id)
        profiles = db.profiles_of([r["blocked_id"] for r in rows])
        return [BlockedPerson(person=summary(profiles.get(r["blocked_id"])), blocked_at=r["created_at"]) for r in rows]

    @router.post("/blocks", status_code=204, responses={**errors, 400: {"model": ErrorResponse}})
    def block(body: UsernameRequest, user: User = signed_in) -> Response:
        """Block someone. Neither of you follows the other any more, and they can't find you."""
        person = visible(body.username, user)
        if person["user_id"] == user.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "That's you.")
        db.block(user.id, person["user_id"])
        return Response(status_code=204)

    @router.delete("/blocks/{username}", status_code=204, responses=errors)
    def unblock(username: str, user: User = signed_in) -> Response:
        person = db.person_by_username(normalise_username(username)[:40])
        if person is None or not db.unblock(user.id, person["user_id"]):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "You haven't blocked anyone with that username.")
        return Response(status_code=204)

    return router

"""Friends: finding someone by username, requests, friendships and blocks.

Everyone is private by default. Someone who isn't your friend sees only your display name,
username and picture; a friend also sees your bio. A block hides each person from the other
completely: to the blocked person, the blocker simply doesn't exist (404, the same as a
username nobody has), so a block can't be detected.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status

from .auth import Auth, RateLimiter, _too_many
from .db import Database, now
from .schemas import (
    BlockedPerson,
    Connection,
    ConnectionList,
    ErrorResponse,
    Leaderboard,
    LeaderboardEntry,
    Person,
    PersonSummary,
    RequestCount,
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
NEED_USERNAME = "Choose a username first, so people know who's asking. You can set one in Settings."


def social_router(db: Database, storage: Storage, auth: Auth) -> APIRouter:
    router = APIRouter(tags=["friends"])
    signed_in = Depends(auth.current_user)
    requests_sent = RateLimiter(db, "friend-request", limit=30, window=timedelta(hours=1))
    lookups = RateLimiter(db, "person-lookup", limit=120, window=timedelta(minutes=10))
    errors = {401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}

    def summary(profile: dict | None) -> PersonSummary:
        profile = profile or {}
        avatar = profile.get("avatar_key")
        return PersonSummary(username=profile.get("username"), display_name=profile.get("display_name"),
                             avatar_url=storage.presign("GET", avatar)[0] if avatar else None)

    def visible(username: str, user: User) -> dict:
        """The person with ``username``, unless there's none or a block either way (both 404)."""
        person = db.person_by_username(normalise_username(username)[:40])
        if person is None or (person["user_id"] != user.id and db.hidden_between(user.id, person["user_id"])):
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
        return person

    def as_connection(row: dict, user: User, profiles: dict[str, dict]) -> Connection:
        other = row["addressee_id"] if row["requester_id"] == user.id else row["requester_id"]
        return Connection(id=row["id"], person=summary(profiles.get(other)), status=row["status"],
                          direction="outgoing" if row["requester_id"] == user.id else "incoming",
                          created_at=row["created_at"], accepted_at=row["accepted_at"])

    def person_view(person: dict, user: User) -> Person:
        if person["user_id"] == user.id:
            return Person(**summary(person).model_dump(), relationship="self", bio=person["bio"])
        conn = db.connection_between(user.id, person["user_id"])
        if conn is None:
            relationship = "none"
        elif conn["status"] == "accepted":
            relationship = "friends"
        else:
            relationship = "requested" if conn["requester_id"] == user.id else "incoming"
        friends = relationship == "friends"
        shared = db.serve_summary(person["user_id"]) if friends and (person["share_stats"] or person["share_positions"]) else None
        return Person(
            **summary(person).model_dump(), relationship=relationship,
            connection_id=conn["id"] if conn else None,
            can_request=relationship == "none" and bool(person["accept_requests"]),
            bio=person["bio"] if friends else None,
            friends_since=conn["accepted_at"] if friends else None,
            # Read when asked, so turning a setting off hides it at once.
            stats=SharedStats(**shared) if shared and person["share_stats"] else None,
            positions=shared["positions"] if shared and person["share_positions"] else None,
        )

    def accepted(requester_id: str, accepter_id: str) -> None:
        """Tell the person who asked; their "sent you a request" is done with."""
        db.forget_notifications_between(requester_id, accepter_id, ("request_received",))
        db.notify(requester_id, "request_accepted", accepter_id)

    def limited(limiter: RateLimiter, user: User) -> None:
        if wait := limiter.retry_after(user.id):
            raise _too_many(wait)
        limiter.hit(user.id)

    @router.get("/people/{username}", response_model=Person, responses={**errors, 429: {"model": ErrorResponse}})
    def get_person(username: str, user: User = signed_in) -> Person:
        """Someone's page: what they show you, and where the two of you stand."""
        limited(lookups, user)
        return person_view(visible(username, user), user)

    @router.get("/connections", response_model=ConnectionList, responses=errors)
    def list_connections(user: User = signed_in) -> ConnectionList:
        rows = db.connections_of(user.id)
        others = [r["addressee_id"] if r["requester_id"] == user.id else r["requester_id"] for r in rows]
        profiles = db.profiles_of(others)
        items = [as_connection(r, user, profiles) for r in rows]
        return ConnectionList(
            friends=[c for c in items if c.status == "accepted"],
            incoming=[c for c in items if c.status == "pending" and c.direction == "incoming"],
            outgoing=[c for c in items if c.status == "pending" and c.direction == "outgoing"],
        )

    @router.get("/connections/count", response_model=RequestCount, responses=errors)
    def count_requests(user: User = signed_in) -> RequestCount:
        """Friend requests waiting for you, for the navigation's badge."""
        return RequestCount(incoming=db.incoming_requests(user.id))

    @router.post("/connections", status_code=201, response_model=Person,
                 responses={**errors, 400: {"model": ErrorResponse}, 403: {"model": ErrorResponse},
                            409: {"model": ErrorResponse}, 429: {"model": ErrorResponse}})
    def send_request(body: UsernameRequest, response: Response, user: User = signed_in) -> Person:
        """Send a friend request. If they'd already asked you, you're friends straight away."""
        if not (db.get_profile(user.id) or {}).get("username"):
            raise HTTPException(status.HTTP_409_CONFLICT, NEED_USERNAME)
        person = visible(body.username, user)
        if person["user_id"] == user.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "That's you.")
        existing = db.connection_between(user.id, person["user_id"])
        if existing and existing["status"] == "pending" and existing["addressee_id"] == user.id:
            db.accept_connection(existing["id"], user.id)
            accepted(existing["requester_id"], user.id)
            response.status_code = status.HTTP_200_OK
            return person_view(person, user)
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, "You're already friends." if existing["status"] == "accepted"
                                else "You've already sent them a request.")
        if not person["accept_requests"]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "They aren't accepting friend requests.")
        limited(requests_sent, user)
        if db.request_connection(user.id, person["user_id"]) == "exists":
            # They asked at the same moment: the two requests meet, and that's a yes from both.
            crossed = db.connection_between(user.id, person["user_id"])
            if crossed and crossed["status"] == "pending" and crossed["addressee_id"] == user.id:
                db.accept_connection(crossed["id"], user.id)
                accepted(crossed["requester_id"], user.id)
            response.status_code = status.HTTP_200_OK
        else:
            db.notify(person["user_id"], "request_received", user.id)
        return person_view(person, user)

    @router.post("/connections/{connection_id}/accept", response_model=Connection, responses=errors)
    def accept_request(connection_id: str, user: User = signed_in) -> Connection:
        """Accept a request someone sent you."""
        row = db.accept_connection(connection_id, user.id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Friend request not found")
        other = row["requester_id"]
        accepted(other, user.id)
        return as_connection(row, user, db.profiles_of([other]))

    @router.delete("/connections/{connection_id}", status_code=204, responses=errors)
    def remove_connection(connection_id: str, user: User = signed_in) -> Response:
        """Cancel a request you sent, decline one you received, or end a friendship."""
        row = db.get_connection(connection_id, user.id)
        if row is None or not db.delete_connection(connection_id, user.id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        # A request that's gone shouldn't still be announced.
        db.forget_notifications_between(row["requester_id"], row["addressee_id"], ("request_received", "request_accepted"))
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
        """Block someone. Any request or friendship between you ends, and they can't find you."""
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

"""Your profile: username, display name, bio and picture, and the stats shown with them.

Only you can see it for now. Once people can connect, a profile is what they'll see of you,
so everything here is written to be shown to others: no email, no notes.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool

from . import keys
from .auth import Auth, RateLimiter, _too_many
from .avatars import MAX_BYTES, AvatarError, clean
from .db import USERNAME_HELD_FOR, Database, now
from .purge import run_purges
from .schemas import (
    ErrorResponse,
    Profile,
    ProfileStats,
    ProfileUpdate,
    User,
    UsernameCheck,
    normalise_username,
    username_problem,
)
from .storage import Storage

TAKEN = "That username is taken."
HELD = "Someone used that username recently, so it's held for them for a while. Try another."
SHARING = ("share_stats", "share_positions", "on_leaderboard")


def profile_router(db: Database, storage: Storage, auth: Auth) -> APIRouter:
    router = APIRouter(prefix="/profile", tags=["profile"])
    signed_in = Depends(auth.current_user)
    pictures = RateLimiter(db, "avatar", limit=20, window=timedelta(hours=1))
    checks = RateLimiter(db, "username-check", limit=120, window=timedelta(minutes=10))
    errors = {401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}}

    def profile_of(user: User) -> Profile:
        row = db.get_profile(user.id) or {}
        avatar = row.get("avatar_key")
        return Profile(
            username=row.get("username"), display_name=row.get("display_name"), bio=row.get("bio"),
            avatar_url=storage.presign("GET", avatar)[0] if avatar else None,
            member_since=user.created_at, stats=ProfileStats(**db.profile_stats(user.id)),
            accept_requests=row.get("accept_requests", True),
            **{k: bool(row.get(k, False)) for k in SHARING},
        )

    def limited(limiter: RateLimiter, user: User) -> None:
        if wait := limiter.retry_after(user.id):
            raise _too_many(wait)
        limiter.hit(user.id)

    @router.get("", response_model=Profile, responses=errors)
    def get_profile(user: User = signed_in) -> Profile:
        return profile_of(user)

    @router.patch("", response_model=Profile, responses={**errors, 409: {"model": ErrorResponse}})
    def update_profile(body: ProfileUpdate, user: User = signed_in) -> Profile:
        """Change the fields sent; leave the rest as they are."""
        fields = body.model_dump(include=body.model_fields_set)
        if fields:
            saved = db.save_profile(user.id, held_for=USERNAME_HELD_FOR, **fields)
            if saved == "username_taken":
                raise HTTPException(status.HTTP_409_CONFLICT, TAKEN)
            if saved == "username_held":
                raise HTTPException(status.HTTP_409_CONFLICT, HELD)
        return profile_of(user)

    @router.get("/username-check", response_model=UsernameCheck,
                responses={**errors, 429: {"model": ErrorResponse}})
    def check_username(username: str, user: User = signed_in) -> UsernameCheck:
        """Whether a username could be yours, for checking as it's typed."""
        limited(checks, user)
        name = normalise_username(username)[:40]
        if problem := username_problem(name):
            return UsernameCheck(username=name, available=False, problem=problem)
        owner = db.username_owner(name)
        if owner not in (None, user.id):
            return UsernameCheck(username=name, available=False, problem=TAKEN)
        hold = db.username_hold(name)
        if hold and hold["user_id"] != user.id and hold["released_at"] > now() - USERNAME_HELD_FOR:
            return UsernameCheck(username=name, available=False, problem=HELD)
        return UsernameCheck(username=name, available=True)

    @router.put("/avatar", response_model=Profile,
                responses={**errors, 413: {"model": ErrorResponse}, 415: {"model": ErrorResponse},
                           429: {"model": ErrorResponse}},
                openapi_extra={"requestBody": {"required": True, "content": {
                    "image/jpeg": {"schema": {"type": "string", "format": "binary"}}}}})
    async def set_avatar(request: Request, user: User = signed_in) -> Profile:
        """A new profile picture: a square JPEG of up to 1 MB, as the browser prepares it."""
        if request.headers.get("content-type", "").split(";")[0].strip() != "image/jpeg":
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Send the picture as a JPEG.")
        await run_in_threadpool(limited, pictures, user)
        body = bytearray()
        async for chunk in request.stream():
            body += chunk
            if len(body) > MAX_BYTES:
                raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Pictures must be under 1 MB.")
        try:
            picture = await run_in_threadpool(clean, bytes(body))
        except AvatarError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        return await run_in_threadpool(_store, user, picture)

    def _store(user: User, picture: bytes) -> Profile:
        old = (db.get_profile(user.id) or {}).get("avatar_key")
        key = keys.avatar_key(user.id, uuid.uuid4().hex)
        with storage.scratch_dir() as work:
            (work / keys.AVATAR).write_bytes(picture)
            storage.publish(work, key.rsplit("/", 1)[0])
        db.save_profile(user.id, avatar_key=key)
        if old:
            run_purges(db, storage, db.queue_purges([old.rsplit("/", 1)[0]]))
        return profile_of(user)

    @router.delete("/avatar", response_model=Profile, responses=errors)
    def remove_avatar(user: User = signed_in) -> Profile:
        old = (db.get_profile(user.id) or {}).get("avatar_key")
        if old:
            db.save_profile(user.id, avatar_key=None)
            run_purges(db, storage, db.queue_purges([old.rsplit("/", 1)[0]]))
        return profile_of(user)

    return router

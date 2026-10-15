"""Notifications: someone sent you a friend request, accepted yours, or sent you a serve.

Messages have their own unread badge, so they aren't repeated here. Notifications from anyone
hidden from you (a block either way, or a suspended account) are left out; ones about a request
that's since been cancelled or declined are deleted with it. They're kept 90 days.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from .auth import Auth
from .convert import person_summary
from .db import Database
from .schemas import ErrorResponse, Notification, UnreadCount, User
from .storage import Storage


def notifications_router(db: Database, storage: Storage, auth: Auth) -> APIRouter:
    router = APIRouter(prefix="/notifications", tags=["notifications"])
    signed_in = Depends(auth.current_user)
    errors = {401: {"model": ErrorResponse}}
    url_for = lambda key: storage.presign("GET", key)[0]  # noqa: E731

    @router.get("", response_model=list[Notification], responses=errors)
    def list_notifications(user: User = signed_in) -> list[Notification]:
        """Your latest 50, newest first."""
        rows = db.notifications_for(user.id)
        people = db.profiles_of(list({r["actor_id"] for r in rows}))
        return [Notification(id=r["id"], kind=r["kind"], person=person_summary(people.get(r["actor_id"]), url_for),
                             conversation_id=r["conversation_id"], created_at=r["created_at"],
                             read=r["read_at"] is not None) for r in rows]

    @router.get("/unread", response_model=UnreadCount, responses=errors)
    def count_unread(user: User = signed_in) -> UnreadCount:
        return UnreadCount(unread=sum(1 for r in db.notifications_for(user.id) if r["read_at"] is None))

    @router.post("/read", status_code=204, responses=errors)
    def mark_read(user: User = signed_in) -> Response:
        """Mark them all read (done when you open the list)."""
        db.mark_notifications_read(user.id)
        return Response(status_code=204)

    return router

"""Messages between friends, and reports of people and messages.

Only friends can message each other, and a message can carry one of the sender's serves,
which the friend can then open read-only for as long as the message exists and they're
friends (db.shared_by). When a friendship ends the conversation stays readable,
but nobody can send to it. A block hides the conversation from both people while it lasts, so
the blocked person still can't tell the blocker exists. Deleting an account deletes the messages
it sent; the other person keeps their side.
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from . import keys
from .auth import Auth, RateLimiter, _too_many
from .db import Database, now
from .posts import visible_kinds
from .schemas import (
    ConversationSummary,
    ErrorResponse,
    Message,
    MessagePage,
    MessagePreview,
    PersonSummary,
    ReceivedServe,
    ReceivedServePage,
    SendMessage,
    SharedServe,
    StartConversation,
    UnreadCount,
    UnseenCount,
    User,
    UserReportRequest,
    normalise_username,
)
from .storage import Storage

NOT_FOUND = "Conversation not found"
FRIENDS_ONLY = "You can only message friends."
PREVIEW = 120
PER_MINUTE, PER_DAY = 30, 500


def _cursor(row: dict) -> str:
    return base64.urlsafe_b64encode(f"{row['created_at'].isoformat()}|{row['id']}".encode()).decode()


def _parse_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        at, message_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|", 1)
        return datetime.fromisoformat(at), message_id
    except Exception as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid cursor") from exc


def messaging_router(db: Database, storage: Storage, auth: Auth) -> APIRouter:
    router = APIRouter(tags=["messages"])
    signed_in = Depends(auth.current_user)
    reports = RateLimiter(db, "user-report", limit=20, window=timedelta(days=1))
    errors = {401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}

    def summary(profile: dict | None) -> PersonSummary | None:
        if not profile:
            return None
        avatar = profile.get("avatar_key")
        return PersonSummary(username=profile.get("username"), display_name=profile.get("display_name"),
                             avatar_url=storage.presign("GET", avatar)[0] if avatar else None)

    def friends(a: str, b: str | None) -> bool:
        return db.are_friends(a, b)

    def mine(conversation_id: str, user: User) -> dict:
        """``user``'s side of the conversation; 404 if they aren't in it or there's a block."""
        member = db.membership(conversation_id, user.id)
        if member is None or (member["other_id"] and db.hidden_between(user.id, member["other_id"])):
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
        return member

    def describe(conversation_id: str, user: User, other_id: str | None, last: dict | None, unread: int) -> ConversationSummary:
        can_send = friends(user.id, other_id)
        why = None if can_send else ("They've deleted their account." if other_id is None else "You're no longer friends.")
        preview = None
        if last:
            text = last["body"]
            if not text and last.get("analysis_id") and last["deleted_at"] is None:
                text = "Sent a serve"
            preview = MessagePreview(text=text[:PREVIEW] if text else None, from_you=last["sender_id"] == user.id,
                                     deleted=last["deleted_at"] is not None, at=last["created_at"])
        other = db.profiles_of([other_id]).get(other_id) if other_id else None
        return ConversationSummary(id=conversation_id, person=summary(other) if other_id else None,
                                   last_message=preview, unread=unread, can_send=can_send, why_not=why)

    def serves_for(rows: list[dict], user: User) -> dict[str, SharedServe]:
        """The serves sent in these messages, as ``user`` may see them."""
        sent = [r for r in rows if r.get("analysis_id")]
        found = db.analyses_by_id([r["analysis_id"] for r in sent])
        out = {}
        for r in sent:
            a = found.get(r["analysis_id"])
            mine = r["sender_id"] == user.id
            # The sender can always see their own serve; the friend only while they may open it.
            ok = a is not None and a["status"] == "succeeded" and (mine or db.shared_by(a["id"], user.id) is not None)
            out[r["id"]] = SharedServe(
                analysis_id=a["id"] if ok else None, available=ok,
                overall_score=a["overall_score"] if ok else None, recorded_at=a["created_at"] if ok else None,
                thumbnail_url=storage.presign("GET", keys.output_key(a["id"], keys.THUMBNAIL))[0] if ok else None)
        return out

    def as_message(row: dict, user: User, serves: dict[str, SharedServe] | None = None) -> Message:
        return Message(id=row["id"], from_you=row["sender_id"] == user.id, body=row["body"],
                       deleted=row["deleted_at"] is not None, created_at=row["created_at"],
                       serve=(serves or {}).get(row["id"]))

    def visible_conversations(user: User) -> list[dict]:
        return [c for c in db.conversations_of(user.id)
                if not (c["other_id"] and db.hidden_between(user.id, c["other_id"]))]

    @router.get("/conversations", response_model=list[ConversationSummary], responses=errors)
    def list_conversations(user: User = signed_in) -> list[ConversationSummary]:
        """Your conversations with messages in them, newest first."""
        return [describe(c["id"], user, c["other_id"], c["last"], c["unread"]) for c in visible_conversations(user)]

    @router.get("/conversations/unread", response_model=UnreadCount, responses=errors)
    def count_unread(user: User = signed_in) -> UnreadCount:
        """Unread messages across all your conversations, for the navigation's badge."""
        return UnreadCount(unread=sum(c["unread"] for c in visible_conversations(user)))

    @router.get("/inbox", response_model=ReceivedServePage, responses={**errors, 422: {"model": ErrorResponse}})
    def received(cursor: str | None = None, limit: int = Query(20, ge=1, le=50), user: User = signed_in) -> ReceivedServePage:
        """Serves your friends sent you, newest first: who, when, whether you've opened it, and
        whether you still can (not once the friendship ends or the serve is deleted)."""
        rows = db.received_serves(user.id, limit + 1, _parse_cursor(cursor) if cursor else None)
        page = rows[:limit]
        serves = serves_for(page, user)
        people = db.profiles_of(list({r["sender_id"] for r in page}))
        return ReceivedServePage(
            items=[ReceivedServe(message_id=r["id"], conversation_id=r["conversation_id"],
                                 sender=summary(people.get(r["sender_id"])) or PersonSummary(),
                                 sent_at=r["created_at"], seen=r["seen_at"] is not None, serve=serves[r["id"]])
                   for r in page],
            next_cursor=_cursor(page[-1]) if len(rows) > limit else None)

    @router.get("/inbox/unseen", response_model=UnseenCount, responses=errors)
    def count_unseen(user: User = signed_in) -> UnseenCount:
        """Serves sent to you that you haven't opened yet and still can, for the Received badge."""
        return UnseenCount(unseen=db.unseen_serves(user.id))

    @router.post("/conversations", response_model=ConversationSummary,
                 responses={**errors, 403: {"model": ErrorResponse}})
    def start_conversation(body: StartConversation, user: User = signed_in) -> ConversationSummary:
        """Open your conversation with a friend, making it the first time."""
        person = db.person_by_username(normalise_username(body.username)[:40])
        if person is None or person["user_id"] == user.id or db.hidden_between(user.id, person["user_id"]):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No one has that username.")
        existing = db.conversation_with(user.id, person["user_id"])
        if existing is None and not friends(user.id, person["user_id"]):
            raise HTTPException(status.HTTP_403_FORBIDDEN, FRIENDS_ONLY)
        conv = existing or db.conversation_with(user.id, person["user_id"], create=True)
        return describe(conv["id"], user, person["user_id"], None, 0)

    @router.get("/conversations/{conversation_id}", response_model=ConversationSummary, responses=errors)
    def get_conversation(conversation_id: str, user: User = signed_in) -> ConversationSummary:
        member = mine(conversation_id, user)
        return describe(conversation_id, user, member["other_id"], None, 0)

    @router.get("/conversations/{conversation_id}/messages", response_model=MessagePage, responses=errors)
    def list_messages(conversation_id: str, before: str | None = None, limit: int = Query(50, ge=1, le=100),
                      user: User = signed_in) -> MessagePage:
        """Newest first; pass ``before`` (the last page's ``next_cursor``) for older ones."""
        member = mine(conversation_id, user)
        rows = db.messages_page(conversation_id, limit + 1, _parse_cursor(before) if before else None)
        page = rows[:limit]
        serves = serves_for(page, user)
        return MessagePage(items=[as_message(r, user, serves) for r in page],
                           next_cursor=_cursor(page[-1]) if len(rows) > limit else None,
                           seen_up_to=member["other_read_at"])

    @router.post("/conversations/{conversation_id}/messages", status_code=201, response_model=Message,
                 responses={**errors, 403: {"model": ErrorResponse}, 429: {"model": ErrorResponse}})
    def send_message(conversation_id: str, body: SendMessage, user: User = signed_in) -> Message:
        member = mine(conversation_id, user)
        if not friends(user.id, member["other_id"]):
            raise HTTPException(status.HTTP_403_FORBIDDEN, FRIENDS_ONLY)
        t = now()
        if db.messages_sent_since(user.id, t - timedelta(minutes=1)) >= PER_MINUTE:
            raise _too_many(60)
        if db.messages_sent_since(user.id, t - timedelta(days=1)) >= PER_DAY:
            raise _too_many(3600)
        if body.analysis_id:
            # Only your own finished analyses can be sent: not one someone shared with you.
            analysis = db.get_owned(body.analysis_id, user.id)
            if analysis is None or analysis["status"] != "succeeded":
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
        row = db.add_message(conversation_id, user.id, body.body, body.analysis_id)
        if body.analysis_id and member["other_id"]:
            db.notify(member["other_id"], "serve_received", user.id, conversation_id)
        return as_message(row, user, serves_for([row], user))

    @router.post("/conversations/{conversation_id}/read", status_code=204, responses=errors)
    def mark_read(conversation_id: str, user: User = signed_in) -> Response:
        mine(conversation_id, user)
        db.mark_read(conversation_id, user.id)
        return Response(status_code=204)

    @router.delete("/messages/{message_id}", status_code=204, responses=errors)
    def delete_message(message_id: str, user: User = signed_in) -> Response:
        """Delete one of your messages for everyone. It shows as "Message deleted"."""
        if not db.delete_message(message_id, user.id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
        return Response(status_code=204)

    @router.post("/reports", status_code=201, responses={**errors, 429: {"model": ErrorResponse}})
    def report(body: UserReportRequest, user: User = signed_in) -> Response:
        """Report someone, or one of their messages to you, for the operator to review. A copy of
        the message is kept with the report, so deleting it doesn't remove the evidence."""
        person = db.person_by_username(normalise_username(body.username)[:40])
        if person is None or person["user_id"] == user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No one has that username.")
        message_body = None
        if body.post_id:  # their post, which you can see
            post = db.get_post(body.post_id)
            if post is None or post["user_id"] != person["user_id"] or post["visibility"] not in visible_kinds(db, user.id, post["user_id"]):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
            message_body = post["caption"]
        if body.comment_id:  # their comment, on a post you can see
            comment = db.get_comment(body.comment_id)
            post = db.get_post(comment["post_id"]) if comment else None
            if comment is None or post is None or comment["user_id"] != person["user_id"] \
                    or post["visibility"] not in visible_kinds(db, user.id, post["user_id"]):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment not found")
            message_body = comment["body"]
        if body.message_id:
            message = db.get_message(body.message_id)
            ok = (message is not None and message["sender_id"] == person["user_id"]
                  and db.membership(message["conversation_id"], user.id) is not None)
            if not ok:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
            message_body = message["body"]
        if wait := reports.retry_after(user.id):
            raise _too_many(wait)
        reports.hit(user.id)
        note = (body.note or "").strip() or None
        db.save_user_report(reporter_id=user.id, reported_id=person["user_id"], reported_username=person["username"],
                            message_id=body.message_id, post_id=body.post_id, comment_id=body.comment_id,
                            message_body=message_body, reason=body.reason, note=note)
        return Response(status_code=201)

    return router

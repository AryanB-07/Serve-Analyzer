"""Posts: a serve you share, with a caption, for everyone signed in or only your friends; likes
and comments.

A post is a snapshot: creating it copies the analysis's skeleton video and thumbnail into the
post's own storage, with its scores. Deleting the post removes exactly that copy (with its likes
and comments); your analysis in My Serves is untouched, and deleting the analysis later doesn't
break the post. A post never carries the analysis's note or filename.

Who can see a post is checked on every request (``viewable``): its author always; for a public
post, anyone signed in who isn't hidden from the author (a block either way, or a suspension);
for a friends post, only the author's current friends. So ending a friendship ends access at
once. Liking and commenting need the same access. Files are served through short-lived signed
URLs, so a link to a friends-only video stops working, and can't be guessed.
"""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from . import keys
from .auth import Auth, _too_many
from .convert import person_summary
from .db import Database, now
from .purge import run_purges
from .schemas import (
    Comment,
    CommentPage,
    CreatePost,
    EditPost,
    ErrorResponse,
    FeedTab,
    LikeState,
    NewComment,
    PersonSummary,
    Post,
    PostPage,
    User,
    normalise_username,
)
from .storage import Storage

NOT_FOUND = "Post not found"
POSTS_PER_DAY = 20
COMMENTS_PER_HOUR = 60


def _cursor(at: datetime, item_id: str) -> str:
    return base64.urlsafe_b64encode(f"{at.isoformat()}|{item_id}".encode()).decode()


def _parse(cursor: str) -> tuple[datetime, str]:
    try:
        at, item_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|", 1)
        return datetime.fromisoformat(at), item_id
    except Exception as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid cursor") from exc


def visible_kinds(db: Database, viewer_id: str, author_id: str) -> tuple[str, ...]:
    """Which of ``author_id``'s posts ``viewer_id`` can see (none if they're hidden from each other)."""
    if viewer_id == author_id:
        return ("public", "friends")
    if db.hidden_between(viewer_id, author_id):
        return ()
    return ("public", "friends") if db.are_friends(viewer_id, author_id) else ("public",)


def posts_router(db: Database, storage: Storage, auth: Auth) -> APIRouter:
    router = APIRouter(tags=["posts"])
    signed_in = Depends(auth.current_user)
    errors = {401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}
    url_for = lambda key: storage.presign("GET", key)[0]  # noqa: E731

    def viewable(post_id: str, user: User) -> dict:
        """The post, if ``user`` may see it; 404 otherwise, the same as no post at all."""
        post = db.get_post(post_id)
        if post is None or post["visibility"] not in visible_kinds(db, user.id, post["user_id"]):
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
        return post

    def as_posts(rows: list[dict], user: User) -> list[Post]:
        counts = db.post_counts([r["id"] for r in rows], user.id)
        authors = db.profiles_of(list({r["user_id"] for r in rows}))
        return [Post(
            id=r["id"], author=person_summary(authors.get(r["user_id"]), url_for) or PersonSummary(),
            is_yours=r["user_id"] == user.id, caption=r["caption"], visibility=r["visibility"], hand=r["hand"],
            overall_score=r["overall_score"], key_scores=r["key_scores"] or None, recorded_at=r["recorded_at"],
            created_at=r["created_at"],
            video_url=url_for(f"{keys.post_prefix(r['id'])}/{keys.POST_VIDEO}"),
            thumbnail_url=url_for(f"{keys.post_prefix(r['id'])}/{keys.POST_THUMBNAIL}"),
            like_count=counts[r["id"]]["likes"], comment_count=counts[r["id"]]["comments"],
            liked_by_you=counts[r["id"]]["liked"],
        ) for r in rows]

    def as_comment(row: dict, post: dict, user: User, authors: dict) -> Comment:
        return Comment(id=row["id"], author=person_summary(authors.get(row["user_id"]), url_for) or PersonSummary(),
                       body=row["body"], created_at=row["created_at"],
                       can_delete=user.id in (row["user_id"], post["user_id"]))

    @router.post("/posts", status_code=201, response_model=Post,
                 responses={**errors, 409: {"model": ErrorResponse}, 429: {"model": ErrorResponse}})
    def create_post(body: CreatePost, user: User = signed_in) -> Post:
        """Post one of your finished serves. Its skeleton video, thumbnail and scores are copied
        into the post; the note and filename aren't."""
        analysis = db.get_owned(body.analysis_id, user.id)
        if analysis is None or analysis["status"] != "succeeded":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
        if not (db.get_profile(user.id) or {}).get("username"):
            raise HTTPException(status.HTTP_409_CONFLICT, "Choose a username first.")
        if db.count_since("posts", user.id, now() - timedelta(days=1)) >= POSTS_PER_DAY:
            raise _too_many(3600)
        post_id = uuid.uuid4().hex
        with storage.scratch_dir() as work:
            for source, target in ((keys.ANNOTATED, keys.POST_VIDEO), (keys.THUMBNAIL, keys.POST_THUMBNAIL)):
                (work / target).write_bytes(storage.read_bytes(keys.output_key(analysis["id"], source)))
            storage.publish(work, keys.post_prefix(post_id))
        ts = now()
        row = db.create_post({
            "id": post_id, "user_id": user.id, "analysis_id": analysis["id"], "caption": body.caption,
            "visibility": body.visibility, "hand": analysis["hand"], "overall_score": analysis["overall_score"],
            "key_scores": analysis["key_scores"], "recorded_at": analysis["created_at"],
            "created_at": ts, "updated_at": ts,
        })
        return as_posts([row], user)[0]

    @router.get("/posts/{post_id}", response_model=Post, responses=errors)
    def get_post(post_id: str, user: User = signed_in) -> Post:
        return as_posts([viewable(post_id, user)], user)[0]

    @router.patch("/posts/{post_id}", response_model=Post, responses=errors)
    def edit_post(post_id: str, body: EditPost, user: User = signed_in) -> Post:
        """Change your post's caption or who can see it."""
        fields = body.model_dump(include=body.model_fields_set)
        if not db.update_post(post_id, user.id, **fields):
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
        return as_posts([db.get_post(post_id)], user)[0]

    @router.delete("/posts/{post_id}", status_code=204, responses=errors)
    def delete_post(post_id: str, user: User = signed_in) -> Response:
        """Delete your post, with its likes, comments and stored video."""
        purge_ids = db.delete_post(post_id, user.id, [keys.post_prefix(post_id)])
        if purge_ids is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
        run_purges(db, storage, purge_ids)
        return Response(status_code=204)

    @router.get("/people/{username}/posts", response_model=PostPage, responses=errors)
    def posts_of(username: str, cursor: str | None = None, limit: int = Query(12, ge=1, le=50),
                 user: User = signed_in) -> PostPage:
        """Someone's posts that you can see, newest first."""
        person = db.person_by_username(normalise_username(username)[:40])
        kinds = visible_kinds(db, user.id, person["user_id"]) if person else ()
        if not kinds:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No one has that username.")
        rows = db.posts_by(person["user_id"], kinds, limit + 1, _parse(cursor) if cursor else None)
        page = rows[:limit]
        return PostPage(items=as_posts(page, user),
                        next_cursor=_cursor(page[-1]["created_at"], page[-1]["id"]) if len(rows) > limit else None)

    @router.get("/feed", response_model=PostPage, responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}})
    def feed(tab: FeedTab = "public", cursor: str | None = None, limit: int = Query(10, ge=1, le=30),
             user: User = signed_in) -> PostPage:
        """Public: everyone's public posts. Friends: posts (public and friends-only) from your
        friends. Newest first, a page at a time; ``cursor`` is the last page's next_cursor."""
        rows = db.feed_page(user.id, tab, limit + 1, _parse(cursor) if cursor else None)
        page = rows[:limit]
        return PostPage(items=as_posts(page, user),
                        next_cursor=_cursor(page[-1]["created_at"], page[-1]["id"]) if len(rows) > limit else None)

    @router.put("/posts/{post_id}/like", response_model=LikeState, responses=errors)
    def like(post_id: str, user: User = signed_in) -> LikeState:
        """Like a post. Liking again changes nothing."""
        viewable(post_id, user)
        db.like(post_id, user.id)
        counts = db.post_counts([post_id], user.id)[post_id]
        return LikeState(liked=True, like_count=counts["likes"])

    @router.delete("/posts/{post_id}/like", response_model=LikeState, responses=errors)
    def unlike(post_id: str, user: User = signed_in) -> LikeState:
        viewable(post_id, user)
        db.unlike(post_id, user.id)
        counts = db.post_counts([post_id], user.id)[post_id]
        return LikeState(liked=False, like_count=counts["likes"])

    @router.get("/posts/{post_id}/comments", response_model=CommentPage, responses=errors)
    def list_comments(post_id: str, cursor: str | None = None, limit: int = Query(30, ge=1, le=100),
                      user: User = signed_in) -> CommentPage:
        """Oldest first; pass ``cursor`` (the last page's next_cursor) for newer ones."""
        post = viewable(post_id, user)
        rows = db.comments_page(post_id, user.id, limit + 1, _parse(cursor) if cursor else None)
        page = rows[:limit]
        authors = db.profiles_of(list({r["user_id"] for r in page}))
        return CommentPage(items=[as_comment(r, post, user, authors) for r in page],
                           next_cursor=_cursor(page[-1]["created_at"], page[-1]["id"]) if len(rows) > limit else None)

    @router.post("/posts/{post_id}/comments", status_code=201, response_model=Comment,
                 responses={**errors, 409: {"model": ErrorResponse}, 429: {"model": ErrorResponse}})
    def add_comment(post_id: str, body: NewComment, user: User = signed_in) -> Comment:
        post = viewable(post_id, user)
        if not (db.get_profile(user.id) or {}).get("username"):
            raise HTTPException(status.HTTP_409_CONFLICT, "Choose a username first.")
        if db.count_since("comments", user.id, now() - timedelta(hours=1)) >= COMMENTS_PER_HOUR:
            raise _too_many(600)
        row = db.add_comment(post_id, user.id, body.body)
        return as_comment(row, post, user, db.profiles_of([user.id]))

    @router.delete("/comments/{comment_id}", status_code=204, responses=errors)
    def delete_comment(comment_id: str, user: User = signed_in) -> Response:
        """Delete your comment, or any comment on your post."""
        comment = db.get_comment(comment_id)
        post = db.get_post(comment["post_id"]) if comment else None
        if comment is None or post is None or user.id not in (comment["user_id"], post["user_id"]):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment not found")
        db.delete_comment(comment_id)
        return Response(status_code=204)

    return router

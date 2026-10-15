"""Email-and-password accounts with server-side sessions in an HttpOnly cookie.

The cookie holds a random token; the database stores only its SHA-256, so a
database leak doesn't hand out live sessions. Sessions last SESSION_TTL from
the last activity, extended at most once per EXTEND_AFTER to avoid a write on
every request.

Emailed links (verification, password reset) work the same way: a random token
in the link, only its hash stored, single use, short-lived. Emails are sent after
the response (a background task), so how long a request takes never reveals
whether an address has an account.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from . import keys
from . import mailer as m
from .convert import api_error
from .db import Database, now
from .purge import analysis_prefixes, run_purges
from .schemas import (
    ChangePasswordRequest,
    ExportedBlock,
    ExportedFollow,
    ExportedConversation,
    ExportedMessage,
    ExportedNotification,
    ExportedProfile,
    ExportedUserReport,
    ChangeEmailRequest,
    ConfirmEmailChangeRequest,
    DataExport,
    DeleteAccountRequest,
    ErrorResponse,
    ExportedAccount,
    ExportedAnalysis,
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    Report,
    SignupRequest,
    User,
    VerifyEmailRequest,
)
from .settings import Settings
from .storage import Storage

SESSION_COOKIE = "serve_session"
SESSION_TTL = timedelta(days=30)
EXTEND_AFTER = timedelta(days=1)
BAD_CREDENTIALS = "Incorrect email or password."
SUSPENDED = "This account is suspended. If you think that's a mistake, contact us (see the Privacy Policy)."
# The date of the current Terms of Service and Privacy Policy (frontend/src/features/legal).
# Change it whenever either document changes materially.
TERMS_VERSION = "2026-10-15"
VERIFY_TTL = timedelta(hours=24)
RESET_TTL = timedelta(hours=1)
BAD_LINK = "This link is invalid or has expired. Request a new one."
EMAIL_TAKEN = "An account with this email already exists."
# Files listed (as download links) in a data export, for a finished analysis.
EXPORTED_OUTPUTS = {"playback_video": keys.PLAYBACK, "annotated_video": keys.ANNOTATED,
                    "thumbnail": keys.THUMBNAIL, "frames": keys.FRAMES}

_hasher = PasswordHasher()
# Verified against when the email is unknown, so both paths take the same time.
_DUMMY_HASH = _hasher.hash(secrets.token_hex(16))


def normalise_email(email: str) -> str:
    return email.strip().lower()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


class RateLimiter:
    """Sliding-window limit per key, counted in the database.

    Every API process shares the same counts, and they survive restarts. Keys
    are stored hashed (with the limiter's scope), so no IPs or emails are kept.
    Two requests racing the limit can both get through; for rate limiting that
    is harmless.
    """

    def __init__(self, db: Database, scope: str, limit: int, window: timedelta) -> None:
        self.db, self.scope, self.limit, self.window = db, scope, limit, window

    def _hash(self, key: str) -> str:
        return hashlib.sha256(f"{self.scope}:{key}".encode()).hexdigest()

    def retry_after(self, key: str) -> float | None:
        """Seconds until ``key`` may try again, or None if it's under the limit."""
        count, oldest = self.db.attempts_since(self._hash(key), now() - self.window)
        if count < self.limit or oldest is None:
            return None
        return max(1.0, (oldest + self.window - now()).total_seconds())

    def hit(self, key: str) -> None:
        self.db.record_attempt(self._hash(key))


def _too_many(seconds: float) -> HTTPException:
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again later.",
        headers={"Retry-After": str(max(1, round(seconds)))},
    )


def _user(row: dict) -> User:
    return User(id=row["id"], email=row["email"], created_at=row["created_at"],
                email_verified=row.get("email_verified_at") is not None)


class Auth:
    def __init__(self, db: Database, settings: Settings, storage: Storage,
                 mailer: m.Mailer | None = None) -> None:
        self.db, self.settings, self.storage = db, settings, storage
        self.mailer = mailer or m.make_mailer(settings)
        self.per_ip = RateLimiter(db, "ip", limit=30, window=timedelta(minutes=10))
        self.failures_per_email = RateLimiter(
            db, "login-failure", limit=10, window=timedelta(minutes=15))
        # Each emailed link costs a send from your mail account, so they're limited per address.
        self.emails_per_user = RateLimiter(db, "email", limit=3, window=timedelta(hours=1))
        # An export reads every result file the account has.
        self.exports_per_user = RateLimiter(db, "export", limit=5, window=timedelta(hours=1))

    def _issue_link(self, user_id: str, purpose: str, ttl: timedelta, path: str,
                    new_email: str | None = None) -> str:
        token = secrets.token_urlsafe(32)
        self.db.create_email_token(user_id, purpose, hash_token(token), now() + ttl, new_email)
        return f"{self.settings.app_url}{path}?token={token}"

    def _check_password(self, user: User, password: str) -> None:
        """For account changes: 403 on a wrong password, limited like failed logins."""
        if wait := self.failures_per_email.retry_after(user.email):
            raise _too_many(wait)
        row = self.db.get_user(user.id)
        if row is None or not verify_password(row["password_hash"], password):
            self.failures_per_email.hit(user.email)
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Incorrect password.")

    def export(self, user: User) -> DataExport:
        """Everything stored for ``user``: the account, and each analysis with its results,
        any report, and download links for its files."""
        row = self.db.get_user(user.id) or {}
        reports = self.db.user_reports(user.id)
        url_for = lambda key: self.storage.presign("GET", key)[0]  # noqa: E731
        items = []
        for a in self.db.all_analyses(user.id):
            files: dict[str, str] = {}
            if a["input_deleted_at"] is None and a["status"] != "awaiting_upload":
                files["original_video"] = url_for(keys.input_key(a["id"], a["content_type"]))
            results = None
            if a["status"] == "succeeded":
                files.update({name: url_for(keys.output_key(a["id"], f))
                              for name, f in EXPORTED_OUTPUTS.items()})
                try:
                    results = json.loads(self.storage.read_bytes(keys.output_key(a["id"], keys.RESULTS)))
                except Exception:  # a missing file shouldn't stop the rest of the export
                    results = None
            report = reports.get(a["id"])
            items.append(ExportedAnalysis(
                id=a["id"], filename=a["filename"], hand=a["hand"], status=a["status"],
                created_at=a["created_at"], camera_view=a.get("camera_view"), note=a.get("note"),
                error=api_error(a["error_code"], a["error_message"]),
                original_video_deleted_at=a["input_deleted_at"], results=results,
                report=Report(**{k: report[k] for k in ("reason", "note", "created_at")}) if report else None,
                files=files,
            ))
        profile = self.db.get_profile(user.id)
        lists = self.db.follow_lists(user.id)
        blocked = self.db.blocked_by(user.id)
        others = self.db.profiles_of([f["user_id"] for f in lists["followers"] + lists["following"]]
                                     + [b["blocked_id"] for b in blocked])
        chats = self.db.conversations_of(user.id)
        others.update(self.db.profiles_of([c["other_id"] for c in chats if c["other_id"]]))
        name_of = lambda uid: (others.get(uid) or {}).get("username")  # noqa: E731
        conversations = [ExportedConversation(
            with_username=name_of(c["other_id"]) if c["other_id"] else None,
            messages=[ExportedMessage(from_you=m["sender_id"] == user.id, body=m["body"], serve=m["analysis_id"],
                                      deleted=m["deleted_at"] is not None, created_at=m["created_at"])
                      for m in reversed(self.db.messages_page(c["id"], limit=100_000))],
        ) for c in chats]
        reports_made = [ExportedUserReport(username=r["reported_username"], reason=r["reason"], note=r["note"],
                                           message=r["message_body"], created_at=r["created_at"])
                        for r in self.db.people_reports(reporter_id=user.id)]
        return DataExport(
            exported_at=now(),
            links_expire_at=now() + timedelta(seconds=self.settings.download_url_ttl_s),
            account=ExportedAccount(
                email=user.email, email_verified=user.email_verified, created_at=user.created_at,
                terms_version=row.get("terms_version"), terms_accepted_at=row.get("terms_accepted_at")),
            profile=ExportedProfile(
                username=profile["username"], display_name=profile["display_name"], bio=profile["bio"],
                allow_follows=profile["allow_follows"], share_stats=profile["share_stats"],
                share_positions=profile["share_positions"], on_leaderboard=profile["on_leaderboard"],
                avatar=url_for(profile["avatar_key"]) if profile["avatar_key"] else None) if profile else None,
            analyses=items,
            following=[ExportedFollow(username=name_of(f["user_id"]), since=f["since"]) for f in lists["following"]],
            followers=[ExportedFollow(username=name_of(f["user_id"]), since=f["since"]) for f in lists["followers"]],
            blocks=[ExportedBlock(username=name_of(b["blocked_id"]), blocked_at=b["created_at"]) for b in blocked],
            conversations=conversations,
            reports_made=reports_made,
            notifications=[ExportedNotification(kind=n["kind"], username=(self.db.profiles_of([n["actor_id"]]).get(n["actor_id"]) or {}).get("username"),
                                                created_at=n["created_at"], read=n["read_at"] is not None)
                           for n in self.db.notifications_for(user.id, limit=10_000)],
        )

    def _send(self, tasks: BackgroundTasks, message: m.Email) -> None:
        tasks.add_task(m.send_quietly, self.mailer, message)

    def _send_verification(self, tasks: BackgroundTasks, user_id: str, email: str) -> None:
        url = self._issue_link(user_id, "verify", VERIFY_TTL, "/verify-email")
        self._send(tasks, m.verification_email(email, url))

    def _clear_cookie(self, response: Response) -> None:
        response.delete_cookie(SESSION_COOKIE, path="/", httponly=True,
                               secure=self.settings.secure_cookies, samesite="lax")

    def _set_cookie(self, response: Response, token: str) -> None:
        response.set_cookie(
            SESSION_COOKIE, token, max_age=int(SESSION_TTL.total_seconds()), path="/",
            httponly=True, secure=self.settings.secure_cookies, samesite="lax",
        )

    def _start_session(self, request: Request, response: Response, user_id: str) -> None:
        # A fresh token on every login, and the old one (if any) revoked: no session fixation.
        if old := request.cookies.get(SESSION_COOKIE):
            self.db.delete_session(hash_token(old))
        token = secrets.token_urlsafe(32)
        self.db.create_session(user_id, hash_token(token), now() + SESSION_TTL)
        self._set_cookie(response, token)

    def _check_ip(self, request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        if wait := self.per_ip.retry_after(ip):
            raise _too_many(wait)
        self.per_ip.hit(ip)

    def current_user(self, request: Request, response: Response) -> User:
        """FastAPI dependency: the signed-in user, or 401."""
        token = request.cookies.get(SESSION_COOKIE)
        session = self.db.get_session(hash_token(token)) if token else None
        if session is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
        if session["user_suspended_at"] is not None:  # suspending ends sessions; this covers a race
            self.db.delete_session(session["token_hash"])
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, SUSPENDED)
        if session["last_seen_at"] < now() - EXTEND_AFTER:
            self.db.extend_session(session["id"], now() + SESSION_TTL)
            self._set_cookie(response, token)
        return User(id=session["user_id"], email=session["user_email"],
                    created_at=session["user_created_at"],
                    email_verified=session["user_email_verified_at"] is not None)

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/auth", tags=["auth"])
        signed_in = Depends(self.current_user)

        @router.post("/signup", status_code=201, response_model=User,
                     responses={409: {"model": ErrorResponse}, 429: {"model": ErrorResponse}})
        def signup(body: SignupRequest, request: Request, response: Response,
                   tasks: BackgroundTasks) -> User:
            """Create an account, sign in, and email a link to confirm the address."""
            self._check_ip(request)
            row = self.db.create_user(normalise_email(body.email), _hasher.hash(body.password),
                                      terms_version=TERMS_VERSION)
            if row is None:
                raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN)
            self._start_session(request, response, row["id"])
            self._send_verification(tasks, row["id"], row["email"])
            self.emails_per_user.hit(row["id"])
            return _user(row)

        @router.post("/login", response_model=User,
                     responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}})
        def login(body: LoginRequest, request: Request, response: Response) -> User:
            self._check_ip(request)
            email = normalise_email(body.email)
            if wait := self.failures_per_email.retry_after(email):
                raise _too_many(wait)
            row = self.db.get_user_by_email(email)
            password_hash = row["password_hash"] if row else _DUMMY_HASH
            if not verify_password(password_hash, body.password) or row is None:
                self.failures_per_email.hit(email)
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_CREDENTIALS)
            # Only after the password checks out, so a suspension says nothing to a guesser.
            if row.get("suspended_at") is not None:
                raise HTTPException(status.HTTP_403_FORBIDDEN, SUSPENDED)
            if _hasher.check_needs_rehash(row["password_hash"]):
                self.db.set_password_hash(row["id"], _hasher.hash(body.password))
            self._start_session(request, response, row["id"])
            return _user(row)

        @router.post("/logout", status_code=204)
        def logout(request: Request) -> Response:
            """End the current session. Succeeds even if not signed in."""
            if token := request.cookies.get(SESSION_COOKIE):
                self.db.delete_session(hash_token(token))
            response = Response(status_code=204)
            self._clear_cookie(response)
            return response

        @router.get("/me", response_model=User, responses={401: {"model": ErrorResponse}})
        def me(user: User = signed_in) -> User:
            return user

        @router.post("/verify-email", status_code=204, responses={400: {"model": ErrorResponse}})
        def verify_email(body: VerifyEmailRequest) -> Response:
            """Confirm an address from the emailed link. Works without signing in, since the
            link may be opened on another device."""
            user_id = self.db.use_email_token(hash_token(body.token), "verify")
            if user_id is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, BAD_LINK)
            self.db.mark_email_verified(user_id)
            return Response(status_code=204)

        @router.post("/verify-email/resend", status_code=202,
                     responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}})
        def resend_verification(tasks: BackgroundTasks, user: User = signed_in) -> Response:
            """Email a fresh confirmation link. Earlier links stop working."""
            if not user.email_verified:
                if wait := self.emails_per_user.retry_after(user.id):
                    raise _too_many(wait)
                self.emails_per_user.hit(user.id)
                self._send_verification(tasks, user.id, user.email)
            return Response(status_code=202)

        @router.post("/password-reset", status_code=202, responses={429: {"model": ErrorResponse}})
        def request_password_reset(body: PasswordResetRequest, request: Request,
                                   tasks: BackgroundTasks) -> Response:
            """Email a reset link if the address has an account. The response is the same
            either way, so it can't be used to find out who has an account."""
            self._check_ip(request)
            row = self.db.get_user_by_email(normalise_email(body.email))
            if row is not None and self.emails_per_user.retry_after(row["id"]) is None:
                self.emails_per_user.hit(row["id"])
                url = self._issue_link(row["id"], "reset", RESET_TTL, "/reset-password")
                self._send(tasks, m.password_reset_email(row["email"], url))
            return Response(status_code=202)

        @router.post("/password-reset/confirm", status_code=204,
                     responses={400: {"model": ErrorResponse}, 429: {"model": ErrorResponse}})
        def confirm_password_reset(body: PasswordResetConfirm, request: Request,
                                   tasks: BackgroundTasks) -> Response:
            """Set a new password from the emailed link. Signs out every device, this one included."""
            self._check_ip(request)
            user_id = self.db.use_email_token(hash_token(body.token), "reset")
            row = self.db.get_user(user_id) if user_id else None
            if row is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, BAD_LINK)
            self.db.reset_password(user_id, _hasher.hash(body.password))
            self._send(tasks, m.password_changed_email(row["email"], self.settings.app_url))
            response = Response(status_code=204)
            self._clear_cookie(response)
            return response

        @router.post("/password-change", status_code=204,
                     responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse},
                                429: {"model": ErrorResponse}})
        def change_password(body: ChangePasswordRequest, request: Request, tasks: BackgroundTasks,
                            user: User = signed_in) -> Response:
            """Change the password from Settings. This device stays signed in; every other one is
            signed out, and any reset link stops working."""
            self._check_password(user, body.current_password)
            token = request.cookies.get(SESSION_COOKIE, "")
            self.db.change_password(user.id, _hasher.hash(body.new_password), keep_session=hash_token(token))
            self._send(tasks, m.password_changed_email(user.email, self.settings.app_url, this_device_kept=True))
            return Response(status_code=204)

        @router.post("/email-change", status_code=202,
                     responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse},
                                403: {"model": ErrorResponse}, 409: {"model": ErrorResponse},
                                429: {"model": ErrorResponse}})
        def request_email_change(body: ChangeEmailRequest, tasks: BackgroundTasks,
                                 user: User = signed_in) -> Response:
            """Email a confirmation link to the new address. The account keeps its current
            address until the link is opened."""
            new_email = normalise_email(body.new_email)
            self._check_password(user, body.password)
            if new_email == user.email:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "That's already your email.")
            # Signup already says when an address is registered, so this reveals nothing new.
            if self.db.get_user_by_email(new_email) is not None:
                raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN)
            if wait := self.emails_per_user.retry_after(user.id):
                raise _too_many(wait)
            self.emails_per_user.hit(user.id)
            url = self._issue_link(user.id, "email_change", VERIFY_TTL, "/confirm-email",
                                   new_email=new_email)
            self._send(tasks, m.email_change_email(new_email, url))
            return Response(status_code=202)

        @router.post("/email-change/confirm", status_code=204,
                     responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
        def confirm_email_change(body: ConfirmEmailChangeRequest, tasks: BackgroundTasks) -> Response:
            """Switch to the new address from the emailed link, and tell the old address.
            Works without signing in, like confirming an email."""
            changed = self.db.change_email(hash_token(body.token))
            if changed == "invalid":
                raise HTTPException(status.HTTP_400_BAD_REQUEST, BAD_LINK)
            if changed == "taken":
                raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN)
            _, old_email, new_email = changed
            self._send(tasks, m.email_changed_notice(old_email, new_email, self.settings.app_url))
            return Response(status_code=204)

        @router.get("/me/export", response_model=DataExport,
                    responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}})
        def export_data(user: User = signed_in) -> JSONResponse:
            """Download everything stored about the account, as one JSON file."""
            if wait := self.exports_per_user.retry_after(user.id):
                raise _too_many(wait)
            self.exports_per_user.hit(user.id)
            data = self.export(user)
            name = f"serve-analyzer-data-{data.exported_at:%Y-%m-%d}.json"
            return JSONResponse(
                data.model_dump(mode="json"),
                headers={"Content-Disposition": f'attachment; filename="{name}"',
                         "Cache-Control": "no-store"},
            )

        @router.delete("/me", status_code=204,
                       responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse},
                                  429: {"model": ErrorResponse}})
        def delete_account(body: DeleteAccountRequest, tasks: BackgroundTasks,
                           user: User = signed_in) -> Response:
            """Permanently delete the account and every video and analysis in it."""
            self._check_password(user, body.password)
            purge_ids = self.db.delete_user(user.id, analysis_prefixes, [keys.avatar_prefix(user.id)])
            run_purges(self.db, self.storage, purge_ids)
            self._send(tasks, m.account_deleted_email(user.email))
            response = Response(status_code=204)
            self._clear_cookie(response)
            return response

        return router


UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def origin_guard(settings: Settings):
    """HTTP middleware refusing cross-origin unsafe requests (CSRF defence in depth).

    Session cookies are SameSite=Lax, which already stops most cross-site
    POSTs; this also covers same-site subdomains and older browsers. Requests
    without an Origin header (non-browser clients) are allowed, because a
    browser always sends one on a cross-origin POST.
    """

    async def middleware(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method in UNSAFE_METHODS and origin is not None:
            same_host = urlsplit(origin).netloc == request.headers.get("host", "")
            if not same_host and origin.rstrip("/") not in settings.allowed_origins:
                return JSONResponse({"detail": "Cross-origin request refused."}, status_code=403)
        return await call_next(request)

    return middleware

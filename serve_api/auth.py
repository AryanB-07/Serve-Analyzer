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
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from . import mailer as m
from .db import Database, now
from .purge import analysis_prefixes, run_purges
from .schemas import (
    DeleteAccountRequest,
    ErrorResponse,
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
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
VERIFY_TTL = timedelta(hours=24)
RESET_TTL = timedelta(hours=1)
BAD_LINK = "This link is invalid or has expired. Request a new one."

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

    def _issue_link(self, user_id: str, purpose: str, ttl: timedelta, path: str) -> str:
        token = secrets.token_urlsafe(32)
        self.db.create_email_token(user_id, purpose, hash_token(token), now() + ttl)
        return f"{self.settings.app_url}{path}?token={token}"

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
            row = self.db.create_user(normalise_email(body.email), _hasher.hash(body.password))
            if row is None:
                raise HTTPException(status.HTTP_409_CONFLICT,
                                    "An account with this email already exists.")
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

        @router.delete("/me", status_code=204,
                       responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse},
                                  429: {"model": ErrorResponse}})
        def delete_account(body: DeleteAccountRequest, tasks: BackgroundTasks,
                           user: User = signed_in) -> Response:
            """Permanently delete the account and every video and analysis in it."""
            if wait := self.failures_per_email.retry_after(user.email):
                raise _too_many(wait)
            row = self.db.get_user(user.id)
            if row is None or not verify_password(row["password_hash"], body.password):
                self.failures_per_email.hit(user.email)
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Incorrect password.")
            purge_ids = self.db.delete_user(user.id, analysis_prefixes)
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

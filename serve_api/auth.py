"""Email-and-password accounts with server-side sessions in an HttpOnly cookie.

The cookie holds a random token; the database stores only its SHA-256, so a
database leak doesn't hand out live sessions. Sessions last SESSION_TTL from
the last activity, extended at most once per EXTEND_AFTER to avoid a write on
every request.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from .db import Database, now
from .schemas import ErrorResponse, LoginRequest, SignupRequest, User
from .settings import Settings

SESSION_COOKIE = "serve_session"
SESSION_TTL = timedelta(days=30)
EXTEND_AFTER = timedelta(days=1)
BAD_CREDENTIALS = "Incorrect email or password."

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
    return User(id=row["id"], email=row["email"], created_at=row["created_at"])


class Auth:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.db, self.settings = db, settings
        self.per_ip = RateLimiter(db, "ip", limit=30, window=timedelta(minutes=10))
        self.failures_per_email = RateLimiter(
            db, "login-failure", limit=10, window=timedelta(minutes=15))

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
                    created_at=session["user_created_at"])

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/auth", tags=["auth"])
        signed_in = Depends(self.current_user)

        @router.post("/signup", status_code=201, response_model=User,
                     responses={409: {"model": ErrorResponse}, 429: {"model": ErrorResponse}})
        def signup(body: SignupRequest, request: Request, response: Response) -> User:
            """Create an account and sign in."""
            self._check_ip(request)
            row = self.db.create_user(normalise_email(body.email), _hasher.hash(body.password))
            if row is None:
                raise HTTPException(status.HTTP_409_CONFLICT,
                                    "An account with this email already exists.")
            self._start_session(request, response, row["id"])
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
            response.delete_cookie(SESSION_COOKIE, path="/", httponly=True,
                                   secure=self.settings.secure_cookies, samesite="lax")
            return response

        @router.get("/me", response_model=User, responses={401: {"model": ErrorResponse}})
        def me(user: User = signed_in) -> User:
            return user

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

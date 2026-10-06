"""Runtime configuration, read from SERVE_API_* environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEV_SECRET = "dev-only-secret"


def _env(name: str, default: str) -> str:
    return os.getenv(f"SERVE_API_{name}", default)


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", "var")))
    secret: str = field(default_factory=lambda: _env("SECRET", DEV_SECRET))
    # "development" allows the built-in secret; anything else requires SERVE_API_SECRET.
    environment: str = field(default_factory=lambda: _env("ENV", "development"))
    # Empty means a SQLite file in data_dir. Postgres: postgresql://user:password@host/db
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", ""))
    # Apply pending migrations when the API starts. Turn off to run them as a
    # separate release step (python -m serve_api.migrate).
    auto_migrate: bool = field(default_factory=lambda: _env("AUTO_MIGRATE", "1") != "0")
    # Prefix the browser uses to reach this API (the Vite dev server proxies /api).
    public_base: str = field(default_factory=lambda: _env("PUBLIC_BASE", "/api"))
    # Session cookies are HTTPS-only except in development. Default: on unless ENV=development.
    cookie_secure: bool | None = field(
        default_factory=lambda: {"1": True, "0": False}.get(_env("COOKIE_SECURE", ""))
    )
    # Unsafe requests (POST/PUT/DELETE) must come from the API's own origin (Origin matching
    # Host), or from one of these, comma-separated. Needed only if a proxy rewrites Host.
    allowed_origins: tuple[str, ...] = field(default_factory=lambda: tuple(
        o.strip().rstrip("/") for o in _env("ALLOWED_ORIGINS", "").split(",") if o.strip()
    ))
    # Each analysis costs real CPU time, so each user gets a budget.
    daily_analysis_limit: int = field(
        default_factory=lambda: int(_env("DAILY_ANALYSIS_LIMIT", "20")))
    max_active_analyses: int = field(
        default_factory=lambda: int(_env("MAX_ACTIVE_ANALYSES", "2")))
    # Where uploads and results live: "local" (data_dir/objects) or "s3".
    storage: str = field(default_factory=lambda: _env("STORAGE", "local"))
    s3_bucket: str = field(default_factory=lambda: _env("S3_BUCKET", ""))
    s3_region: str = field(default_factory=lambda: _env("S3_REGION", ""))
    # Only for S3-compatible services (R2, MinIO); empty means AWS.
    s3_endpoint_url: str = field(default_factory=lambda: _env("S3_ENDPOINT_URL", ""))
    # Where people open the app, for links in emails (no trailing slash). Vite's dev server by default.
    app_url: str = field(default_factory=lambda: _env("APP_URL", "http://localhost:5173").rstrip("/"))
    # Outgoing email over SMTP. With no host, emails are written to data_dir/outbox instead
    # (development only). Gmail: host smtp.gmail.com, port 587, the account's address as the
    # username and an app password (https://myaccount.google.com/apppasswords).
    smtp_host: str = field(default_factory=lambda: _env("SMTP_HOST", ""))
    smtp_port: int = field(default_factory=lambda: int(_env("SMTP_PORT", "587")))
    smtp_username: str = field(default_factory=lambda: _env("SMTP_USERNAME", ""))
    smtp_password: str = field(default_factory=lambda: _env("SMTP_PASSWORD", ""))
    # The From address; defaults to the SMTP username.
    email_from: str = field(default_factory=lambda: _env("EMAIL_FROM", ""))
    # Must people confirm their email before analysing? Default: yes unless ENV=development.
    verify_email: bool | None = field(
        default_factory=lambda: {"1": True, "0": False}.get(_env("REQUIRE_VERIFIED_EMAIL", ""))
    )
    # Original uploads are deleted this many days after upload (0 keeps them). Results,
    # including their own playback copy of the video, are kept until the person deletes them.
    upload_retention_days: int = field(
        default_factory=lambda: int(_env("UPLOAD_RETENTION_DAYS", "30")))
    max_upload_bytes: int = 200 * 1024 * 1024
    upload_url_ttl_s: int = 15 * 60
    # Long enough that seeking (new Range requests) keeps working while a results page is open.
    download_url_ttl_s: int = 6 * 60 * 60

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url or f"sqlite:///{self.data_dir / 'serve_api.sqlite3'}"
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
        return url

    @property
    def secure_cookies(self) -> bool:
        return self.environment != "development" if self.cookie_secure is None else self.cookie_secure

    @property
    def require_verified_email(self) -> bool:
        return self.environment != "development" if self.verify_email is None else self.verify_email

    @property
    def sender(self) -> str:
        return self.email_from or self.smtp_username

    @property
    def outbox_dir(self) -> Path:
        return self.data_dir / "outbox"

    @property
    def objects_dir(self) -> Path:
        return self.data_dir / "objects"

    def check(self) -> None:
        """Refuse to run a non-development deployment with the default secret or without email."""
        if self.environment == "development":
            return
        missing = [name for name, unset in (
            ("SERVE_API_SECRET", self.secret == DEV_SECRET),
            # Without email nobody can verify their address or reset a password.
            ("SERVE_API_SMTP_HOST", not self.smtp_host),
            ("SERVE_API_EMAIL_FROM or SERVE_API_SMTP_USERNAME", not self.sender),
            ("SERVE_API_APP_URL", self.app_url.startswith("http://localhost")),
        ) if unset]
        if missing:
            raise RuntimeError(
                f"{', '.join(missing)} must be set when SERVE_API_ENV is {self.environment!r}"
            )

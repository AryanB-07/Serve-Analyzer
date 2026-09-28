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
    def objects_dir(self) -> Path:
        return self.data_dir / "objects"

    def check(self) -> None:
        """Refuse to run a non-development deployment with the public default secret."""
        if self.environment != "development" and self.secret == DEV_SECRET:
            raise RuntimeError(
                f"SERVE_API_SECRET must be set when SERVE_API_ENV is {self.environment!r}"
            )

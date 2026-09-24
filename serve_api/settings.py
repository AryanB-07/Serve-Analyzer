"""Runtime configuration, read from SERVE_API_* environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("SERVE_API_DATA_DIR", "var")))
    secret: str = field(default_factory=lambda: os.getenv("SERVE_API_SECRET", "dev-only-secret"))
    # Prefix the browser uses to reach this API (the Vite dev server proxies /api).
    public_base: str = field(default_factory=lambda: os.getenv("SERVE_API_PUBLIC_BASE", "/api"))
    max_upload_bytes: int = 200 * 1024 * 1024
    upload_url_ttl_s: int = 15 * 60
    # Long enough that seeking (new Range requests) keeps working while a results page is open.
    download_url_ttl_s: int = 6 * 60 * 60

    @property
    def db_path(self) -> Path:
        return self.data_dir / "serve_api.sqlite3"

    @property
    def objects_dir(self) -> Path:
        return self.data_dir / "objects"

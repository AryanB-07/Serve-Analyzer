"""Local object storage with S3-style presigned URLs.

The browser uploads and downloads with short-lived signed URLs, exactly as
it would against S3, so swapping in S3 later changes only this module.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, urlencode

from .settings import Settings


class StorageError(Exception):
    pass


class LocalStorage:
    def __init__(self, settings: Settings) -> None:
        self.root = settings.objects_dir.resolve()
        self.secret = settings.secret.encode()
        self.public_base = settings.public_base.rstrip("/")
        self.ttl = {"PUT": settings.upload_url_ttl_s, "GET": settings.download_url_ttl_s}
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise StorageError(f"Invalid key: {key}")
        return path

    def exists(self, key: str) -> bool:
        return self.path(key).is_file()

    def _signature(self, method: str, key: str, expires: int, content_type: str) -> str:
        message = f"{method}\n{key}\n{expires}\n{content_type}".encode()
        return hmac.new(self.secret, message, hashlib.sha256).hexdigest()

    def presign(self, method: str, key: str, content_type: str = "") -> tuple[str, int]:
        """Return (url, expires_at_unix).

        GET expiries are rounded up to the hour so the URL for an object stays
        identical between requests and the browser's HTTP cache can reuse it.
        """
        expires = int(time.time()) + self.ttl[method]
        if method == "GET":
            expires = -(-expires // 3600) * 3600
        sig = self._signature(method, key, expires, content_type)
        query = urlencode({"expires": expires, "sig": sig})
        return f"{self.public_base}/storage/{quote(key)}?{query}", expires

    def verify(self, method: str, key: str, expires: int, sig: str, content_type: str = "") -> bool:
        if expires < time.time():
            return False
        expected = self._signature(method, key, expires, content_type)
        return hmac.compare_digest(expected, sig)

    async def write_stream(self, key: str, chunks, max_bytes: int) -> int:
        """Stream an upload to disk atomically; raises StorageError if too large."""
        dest = self.path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=dest.parent, suffix=".part")
        written = 0
        try:
            with os.fdopen(fd, "wb") as f:
                async for chunk in chunks:
                    written += len(chunk)
                    if written > max_bytes:
                        raise StorageError(f"Upload exceeds {max_bytes} bytes")
                    f.write(chunk)
            os.replace(tmp, dest)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        return written

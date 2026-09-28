"""Object storage for uploads and pipeline outputs: local disk or S3.

The browser uploads and downloads with short-lived presigned URLs in both
cases, so it never talks to the API for video bytes. Locally the API serves
those URLs itself (the /storage routes); with S3 they point at the bucket.

The worker runs the pipeline in a private scratch folder and publishes the
outputs only while it still holds the job's claim, so a stalled worker can
never overwrite the files of the worker that took its job over.
"""

from __future__ import annotations

import hashlib
import hmac
import mimetypes
import os
import shutil
import tempfile
import time
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, urlencode

from .settings import Settings


class StorageError(Exception):
    pass


class Storage(Protocol):
    def presign(self, method: str, key: str, content_type: str = "") -> tuple[str, int]:
        """(url, expires_at_unix) for the browser to PUT or GET ``key``."""

    def size(self, key: str) -> int | None:
        """Size in bytes, or None if there is no such object."""

    def read_bytes(self, key: str) -> bytes: ...

    def local_copy(self, key: str) -> AbstractContextManager[Path]:
        """A local file path holding the object, valid inside the ``with`` block."""

    def scratch_dir(self) -> AbstractContextManager[Path]:
        """An empty private folder for the worker, removed afterwards."""

    def publish(self, local_dir: Path, prefix: str) -> None:
        """Put every file in ``local_dir`` under ``prefix``, replacing any already there."""

    def delete_prefix(self, prefix: str) -> None: ...


def make_storage(settings: Settings) -> Storage:
    if settings.storage == "s3":
        return S3Storage(settings)
    if settings.storage == "local":
        return LocalStorage(settings)
    raise ValueError(f"Unknown storage backend {settings.storage!r} (use 'local' or 's3')")


class LocalStorage:
    """Files under data_dir/objects, with HMAC-signed URLs the API itself verifies."""

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

    def size(self, key: str) -> int | None:
        path = self.path(key)
        return path.stat().st_size if path.is_file() else None

    def read_bytes(self, key: str) -> bytes:
        return self.path(key).read_bytes()

    @contextmanager
    def local_copy(self, key: str) -> Iterator[Path]:
        yield self.path(key)

    @contextmanager
    def scratch_dir(self) -> Iterator[Path]:
        # On the same filesystem as the objects, so publishing is a rename.
        parent = self.root / ".scratch"
        parent.mkdir(exist_ok=True)
        path = Path(tempfile.mkdtemp(dir=parent))
        try:
            yield path
        finally:
            shutil.rmtree(path, ignore_errors=True)

    def publish(self, local_dir: Path, prefix: str) -> None:
        dest = self.path(prefix)
        dest.mkdir(parents=True, exist_ok=True)
        for file in local_dir.iterdir():
            if file.is_file():
                os.replace(file, dest / file.name)  # atomic per file

    def delete_prefix(self, prefix: str) -> None:
        shutil.rmtree(self.path(prefix), ignore_errors=True)

    def _signature(self, method: str, key: str, expires: int, content_type: str) -> str:
        message = f"{method}\n{key}\n{expires}\n{content_type}".encode()
        return hmac.new(self.secret, message, hashlib.sha256).hexdigest()

    def presign(self, method: str, key: str, content_type: str = "") -> tuple[str, int]:
        """GET expiries are rounded up to the hour so the URL for an object stays
        identical between requests and the browser's HTTP cache can reuse it."""
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


class S3Storage:
    """An S3 bucket (or anything S3-compatible: R2, MinIO) via presigned URLs.

    Credentials come from the usual AWS sources (environment variables, an
    instance or task role). The bucket needs a CORS rule allowing PUT from the
    app's origin; see docs/deployment.md.
    """

    def __init__(self, settings: Settings) -> None:
        import boto3
        from botocore.config import Config

        if not settings.s3_bucket:
            raise ValueError("SERVE_API_S3_BUCKET must be set when SERVE_API_STORAGE=s3")
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            region_name=settings.s3_region or None,
            endpoint_url=settings.s3_endpoint_url or None,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}
                          if settings.s3_endpoint_url else {}),
        )
        self.ttl = {"PUT": settings.upload_url_ttl_s, "GET": settings.download_url_ttl_s}

    def presign(self, method: str, key: str, content_type: str = "") -> tuple[str, int]:
        params = {"Bucket": self.bucket, "Key": key}
        if method == "PUT":
            params["ContentType"] = content_type
        operation = {"PUT": "put_object", "GET": "get_object"}[method]
        url = self.client.generate_presigned_url(operation, Params=params, ExpiresIn=self.ttl[method])
        return url, int(time.time()) + self.ttl[method]

    def size(self, key: str) -> int | None:
        from botocore.exceptions import ClientError

        try:
            return self.client.head_object(Bucket=self.bucket, Key=key)["ContentLength"]
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return None
            raise

    def read_bytes(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    @contextmanager
    def local_copy(self, key: str) -> Iterator[Path]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / Path(key).name
            self.client.download_file(self.bucket, key, str(path))
            yield path

    @contextmanager
    def scratch_dir(self) -> Iterator[Path]:
        with tempfile.TemporaryDirectory() as tmp:
            yield Path(tmp)

    def publish(self, local_dir: Path, prefix: str) -> None:
        for file in local_dir.iterdir():
            if file.is_file():
                content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
                self.client.upload_file(str(file), self.bucket, f"{prefix}/{file.name}",
                                        ExtraArgs={"ContentType": content_type})

    def delete_prefix(self, prefix: str) -> None:
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix.rstrip("/") + "/"):
            objects = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if objects:
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": objects})

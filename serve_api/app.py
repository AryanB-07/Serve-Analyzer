"""FastAPI application. Run with: uvicorn serve_api.app:create_app --factory --reload"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text

from . import keys, migrate
from .auth import Auth, origin_guard
from .mailer import Mailer
from .purge import analysis_prefixes, run_purges
from .convert import result_from_file, summary_from_row
from .db import Database, now
from .schemas import (
    AnalysisList,
    AnalysisResult,
    AnalysisSummary,
    CreateAnalysisRequest,
    CreateAnalysisResponse,
    ErrorResponse,
    FramesPayload,
    UploadTarget,
    User,
)
from .settings import Settings
from .storage import LocalStorage, StorageError, make_storage

IMMUTABLE = "private, max-age=31536000, immutable"
UNAUTHORIZED = {401: {"model": ErrorResponse}}
ERRORS = {**UNAUTHORIZED, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}}
LIMITED = {**ERRORS, 429: {"model": ErrorResponse}}


def _encode_cursor(row: dict) -> str:
    return base64.urlsafe_b64encode(f"{row['created_at'].isoformat()}|{row['id']}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        created_at, analysis_id = base64.urlsafe_b64decode(cursor).decode().split("|")
        return datetime.fromisoformat(created_at), analysis_id
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid cursor") from exc


VERIFY_FIRST = ("Confirm your email address to analyze serves. Check your inbox for the link, "
                "or send a new one from your account page.")


def create_app(settings: Settings | None = None, mailer: Mailer | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.check()
    db = Database(settings.sqlalchemy_url)
    if settings.auto_migrate:
        migrate.upgrade(db.engine)
    storage = make_storage(settings)
    auth = Auth(db, settings, storage, mailer)

    app = FastAPI(title="Serve Analyzer API", version="1.0.0")
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.middleware("http")(origin_guard(settings))
    app.include_router(auth.router())
    app.state.auth = auth
    signed_in = Depends(auth.current_user)

    def get_row(analysis_id: str, user: User) -> dict:
        # Someone else's analysis is "not found" too, so IDs can't be probed.
        row = db.get_owned(analysis_id, user.id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
        return row

    def queue_within_limit(analysis_id: str, user: User, from_status: str, conflict: str,
                           **fields) -> None:
        outcome = db.transition_within_limit(
            analysis_id, user.id, (from_status,), "queued", settings.max_active_analyses, **fields)
        if outcome == "conflict":
            raise HTTPException(status.HTTP_409_CONFLICT, conflict)
        if outcome == "limit":
            n = settings.max_active_analyses
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"You already have {n} {'analysis' if n == 1 else 'analyses'} in progress. "
                "Wait for one to finish, then try again.",
            )

    def signed_get(key: str) -> str:
        return storage.presign("GET", key)[0]

    def succeeded_row(analysis_id: str, user: User) -> dict:
        row = get_row(analysis_id, user)
        if row["status"] != "succeeded":
            raise HTTPException(status.HTTP_409_CONFLICT, f"Analysis is {row['status']}")
        return row

    @app.get("/health", include_in_schema=False)
    def health() -> JSONResponse:
        """For load balancers and uptime checks: fails if the database is unreachable."""
        try:
            with db.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse({"status": "database unavailable"}, status_code=503)
        return JSONResponse({"status": "ok"})

    @app.post("/analyses", status_code=201, response_model=CreateAnalysisResponse,
              responses={**UNAUTHORIZED, 403: {"model": ErrorResponse}, 413: {"model": ErrorResponse},
                         429: {"model": ErrorResponse}})
    def create_analysis(
        body: CreateAnalysisRequest, user: User = signed_in
    ) -> CreateAnalysisResponse:
        """Create a record and return a presigned URL to PUT the video to."""
        if settings.require_verified_email and not user.email_verified:
            raise HTTPException(status.HTTP_403_FORBIDDEN, VERIFY_FIRST)
        if body.size_bytes > settings.max_upload_bytes:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                f"Videos must be under {settings.max_upload_bytes // (1024 * 1024)} MB",
            )
        row = db.create_within_limit(
            user.id, body.hand, body.filename, body.content_type, body.size_bytes,
            since=now() - timedelta(days=1), limit=settings.daily_analysis_limit,
        )
        if row is None:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"You can analyze up to {settings.daily_analysis_limit} serves a day. "
                "Try again tomorrow.",
            )
        key = keys.input_key(row["id"], body.content_type)
        url, expires = storage.presign("PUT", key, body.content_type)
        return CreateAnalysisResponse(
            analysis=summary_from_row(row, signed_get),
            upload=UploadTarget(
                url=url,
                headers={"Content-Type": body.content_type},
                expires_at=datetime.fromtimestamp(expires, UTC),
            ),
        )

    @app.get("/analyses", response_model=AnalysisList, responses=UNAUTHORIZED)
    def list_analyses(
        limit: Annotated[int, Query(ge=1, le=100)] = 20, cursor: str | None = None,
        user: User = signed_in,
    ) -> AnalysisList:
        rows = db.list(user.id, limit + 1, _decode_cursor(cursor) if cursor else None)
        page = rows[:limit]
        return AnalysisList(
            items=[summary_from_row(r, signed_get) for r in page],
            next_cursor=_encode_cursor(page[-1]) if len(rows) > limit else None,
        )

    @app.get("/analyses/{analysis_id}", response_model=AnalysisSummary, responses=ERRORS)
    def get_analysis(analysis_id: str, user: User = signed_in) -> AnalysisSummary:
        return summary_from_row(get_row(analysis_id, user), signed_get)

    @app.post("/analyses/{analysis_id}/start", status_code=202, response_model=AnalysisSummary,
              responses=LIMITED)
    def start_analysis(analysis_id: str, user: User = signed_in) -> AnalysisSummary:
        """Queue the analysis once the upload has finished."""
        row = get_row(analysis_id, user)
        input_key = keys.input_key(analysis_id, row["content_type"])
        size = storage.size(input_key)
        if size is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "The video has not been uploaded yet")
        if size > settings.max_upload_bytes:
            # A presigned S3 PUT can't cap the size, so it's checked here instead.
            storage.delete_prefix(keys.upload_prefix(analysis_id))
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                f"Videos must be under {settings.max_upload_bytes // (1024 * 1024)} MB",
            )
        queue_within_limit(analysis_id, user, "awaiting_upload",
                           f"Analysis is already {row['status']}")
        return summary_from_row(get_row(analysis_id, user), signed_get)

    @app.post("/analyses/{analysis_id}/retry", status_code=202, response_model=AnalysisSummary,
              responses=LIMITED)
    def retry_analysis(analysis_id: str, user: User = signed_in) -> AnalysisSummary:
        row = get_row(analysis_id, user)
        queue_within_limit(analysis_id, user, "failed",
                           f"Only failed analyses can be retried; this one is {row['status']}",
                           attempts=0)
        return summary_from_row(get_row(analysis_id, user), signed_get)

    @app.delete("/analyses/{analysis_id}", status_code=204, responses=ERRORS)
    def delete_analysis(analysis_id: str, user: User = signed_in) -> Response:
        """Delete an analysis with its video and results, whatever its status.

        If a worker is processing it, the worker finds the job gone and stops: its
        status writes no longer match a row, and anything it publishes is removed.
        """
        purge_ids = db.delete_analysis(analysis_id, user.id, analysis_prefixes(analysis_id))
        if purge_ids is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
        run_purges(db, storage, purge_ids)
        return Response(status_code=204)

    @app.get("/analyses/{analysis_id}/result", response_model=AnalysisResult, responses=ERRORS)
    def get_result(analysis_id: str, user: User = signed_in) -> AnalysisResult:
        succeeded_row(analysis_id, user)
        results = json.loads(storage.read_bytes(keys.output_key(analysis_id, keys.RESULTS)))
        return result_from_file(analysis_id, results, signed_get)

    @app.get("/analyses/{analysis_id}/frames", response_model=FramesPayload,
             responses=ERRORS)
    def get_frames(analysis_id: str, user: User = signed_in) -> Response:
        """Per-frame landmarks and metric series.

        Served straight from the pipeline's frames.json (validated against
        FramesPayload in tests) to avoid re-parsing a large payload per request.
        """
        succeeded_row(analysis_id, user)
        return Response(
            storage.read_bytes(keys.output_key(analysis_id, keys.FRAMES)),
            media_type="application/json",
            headers={"Cache-Control": IMMUTABLE},
        )

    if isinstance(storage, LocalStorage):
        _mount_local_storage(app, storage, db, settings)
    return app


def _mount_local_storage(
    app: FastAPI, storage: LocalStorage, db: Database, settings: Settings
) -> None:
    """Serve the local backend's presigned URLs. (With S3 the bucket serves them.)"""

    @app.put("/storage/{key:path}", status_code=204, include_in_schema=False)
    async def put_object(key: str, request: Request, expires: int, sig: str) -> Response:
        content_type = request.headers.get("content-type", "")
        if not storage.verify("PUT", key, expires, sig, content_type):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid or expired upload URL")
        # A signed URL stays valid until it expires; refuse to replace the video
        # once the analysis has been started (the worker may be reading it).
        analysis_id = key.split("/")[1] if key.startswith("uploads/") else ""
        row = db.get(analysis_id)
        if row is None or row["status"] != "awaiting_upload":
            raise HTTPException(status.HTTP_409_CONFLICT, "This upload is closed")
        try:
            await storage.write_stream(key, request.stream(), settings.max_upload_bytes)
        except StorageError as exc:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(exc)) from exc
        return Response(status_code=204)

    @app.get("/storage/{key:path}", include_in_schema=False)
    def get_object(key: str, expires: int, sig: str) -> FileResponse:
        if not storage.verify("GET", key, expires, sig):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid or expired URL")
        path = storage.path(key)
        if not path.is_file():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        return FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})

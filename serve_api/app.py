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
from .error_reporting import init_error_reporting
from .mailer import Mailer
from .messaging import messaging_router
from .notifications import notifications_router
from .posts import posts_router
from .profile import profile_router
from .purge import analysis_prefixes, run_purges
from .convert import as_shared, person_summary, result_from_file, summary_from_row
from .db import Database, HistoryFilters, now
from .schemas import (
    AnalysisList,
    AnalysisResult,
    AnalysisSummary,
    CreateAnalysisRequest,
    CreateAnalysisResponse,
    FAILED_REASONS,
    SUCCEEDED_REASONS,
    ErrorResponse,
    FramesPayload,
    KeyPosition,
    NoteRequest,
    Report,
    ReportRequest,
    ScoreBand,
    UploadTarget,
    User,
)
from .settings import Settings
from .social import social_router
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
                "or send a new one from Settings.")


def create_app(settings: Settings | None = None, mailer: Mailer | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.check()
    init_error_reporting(settings, "api")
    db = Database(settings.sqlalchemy_url)
    if settings.auto_migrate:
        migrate.upgrade(db.engine)
    storage = make_storage(settings)
    auth = Auth(db, settings, storage, mailer)

    # The interactive docs (/docs, /redoc, /openapi.json) only in development: a live site has
    # no reason to publish a map of its API. app.openapi() still works for scripts/export_openapi.py.
    dev = settings.environment == "development"
    app = FastAPI(title="Serve Analyzer API", version="1.0.0", docs_url="/docs" if dev else None,
                  redoc_url="/redoc" if dev else None, openapi_url="/openapi.json" if dev else None)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.middleware("http")(origin_guard(settings))
    app.include_router(auth.router())
    app.include_router(profile_router(db, storage, auth))
    # Before social_router: /people/{username}/posts must match before /people/{username}/{kind}.
    app.include_router(posts_router(db, storage, auth))
    app.include_router(social_router(db, storage, auth))
    app.include_router(messaging_router(db, storage, auth))
    app.include_router(notifications_router(db, storage, auth))
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

    def readable_row(analysis_id: str, user: User) -> tuple[dict, str | None]:
        """For reading only (summary, results, frames): your own analysis, or one a friend sent
        you that you can still open (db.shared_by). Returns the row and who shared it (None if
        it's yours). Anything else is "not found", as for get_row."""
        row = db.get_owned(analysis_id, user.id)
        if row is not None:
            return row, None
        sharer = db.shared_by(analysis_id, user.id)
        row = db.get(analysis_id) if sharer else None
        if row is None or row["status"] != "succeeded":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
        return row, sharer

    def readable_summary(row: dict, sharer: str | None) -> AnalysisSummary:
        summary = summary_from_row(row, signed_get)
        if sharer is None:
            return summary
        return as_shared(summary, person_summary(db.get_profile(sharer), signed_get))

    @app.get("/health", include_in_schema=False)
    def health() -> JSONResponse:
        """For load balancers and uptime checks: fails if the database is unreachable."""
        try:
            with db.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse({"status": "database unavailable"}, status_code=503)
        return JSONResponse({"status": "ok"})

    @app.get("/health/queue", include_in_schema=False)
    def queue_health() -> JSONResponse:
        """For an uptime monitor: 503 when analyses are waiting too long, which means the
        workers have stopped (or can't keep up). /health alone can't see that."""
        stats = db.queue_stats()
        stuck = stats["oldest_queued_s"] > settings.queue_alert_after_s
        return JSONResponse({"status": "stuck" if stuck else "ok", **stats},
                            status_code=503 if stuck else 200)

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
            camera_view=body.camera_view,
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
        uploaded_from: Annotated[datetime | None, Query(description="uploaded at or after")] = None,
        uploaded_to: Annotated[datetime | None, Query(description="uploaded before")] = None,
        min_score: Annotated[int | None, Query(ge=0, le=100)] = None,
        max_score: Annotated[int | None, Query(ge=0, le=100)] = None,
        stat: KeyPosition | None = None,
        stat_band: ScoreBand | None = None,
        user: User = signed_in,
    ) -> AnalysisList:
        """History, newest first, optionally filtered. Score filters only match scored analyses."""
        if (stat is None) != (stat_band is None):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "stat and stat_band go together")
        filters = HistoryFilters(uploaded_from, uploaded_to, min_score, max_score, stat, stat_band)
        rows = db.list(user.id, limit + 1, _decode_cursor(cursor) if cursor else None, filters)
        page = rows[:limit]
        return AnalysisList(
            items=[summary_from_row(r, signed_get) for r in page],
            next_cursor=_encode_cursor(page[-1]) if len(rows) > limit else None,
        )

    @app.get("/analyses/{analysis_id}", response_model=AnalysisSummary, responses=ERRORS)
    def get_analysis(analysis_id: str, user: User = signed_in) -> AnalysisSummary:
        row, sharer = readable_row(analysis_id, user)
        if sharer:  # a friend's serve, opened: it's seen in your Received view
            db.mark_serve_seen(analysis_id, user.id)
        return readable_summary(row, sharer)

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
        if row["status"] == "failed" and (
            row["input_deleted_at"] is not None
            or storage.size(keys.input_key(analysis_id, row["content_type"])) is None
        ):
            why = (f"Original videos are kept for {settings.upload_retention_days} days"
                   if row["input_deleted_at"] is not None else "The original video is no longer stored")
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{why}, so this analysis can't be retried. Upload the video again instead.",
            )
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

    @app.put("/analyses/{analysis_id}/note", response_model=AnalysisSummary, responses=ERRORS)
    def set_note(analysis_id: str, body: NoteRequest, user: User = signed_in) -> AnalysisSummary:
        """Add, change or (with an empty note) remove your own note on an analysis."""
        note = (body.note or "").strip() or None
        if not db.set_note(analysis_id, user.id, note):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
        return summary_from_row(get_row(analysis_id, user), signed_get)

    @app.put("/analyses/{analysis_id}/report", response_model=Report,
             responses={**ERRORS, 422: {"model": ErrorResponse}})
    def report_analysis(analysis_id: str, body: ReportRequest, user: User = signed_in) -> Report:
        """Tell us this result looks wrong. Sending another replaces the previous report."""
        row = get_row(analysis_id, user)
        allowed = {"succeeded": SUCCEEDED_REASONS, "failed": FAILED_REASONS}.get(row["status"])
        if allowed is None:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "Wait for the analysis to finish before reporting a problem.")
        if body.reason not in allowed:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                f"{body.reason!r} doesn't apply to a {row['status']} analysis.")
        note = (body.note or "").strip() or None
        saved = db.save_report(row, body.reason, note)
        return Report(reason=saved["reason"], note=saved["note"], created_at=saved["created_at"])

    @app.get("/analyses/{analysis_id}/report", response_model=Report | None, responses=ERRORS)
    def get_report(analysis_id: str, user: User = signed_in) -> Report | None:
        """The report sent about this analysis, or null."""
        get_row(analysis_id, user)
        saved = db.get_report(analysis_id)
        return Report(**{k: saved[k] for k in ("reason", "note", "created_at")}) if saved else None

    @app.get("/analyses/{analysis_id}/result", response_model=AnalysisResult, responses=ERRORS)
    def get_result(analysis_id: str, user: User = signed_in) -> AnalysisResult:
        row, sharer = readable_row(analysis_id, user)
        if sharer is None and row["status"] != "succeeded":
            raise HTTPException(status.HTTP_409_CONFLICT, f"Analysis is {row['status']}")
        results = json.loads(storage.read_bytes(keys.output_key(analysis_id, keys.RESULTS)))
        return result_from_file(analysis_id, results, signed_get)

    @app.get("/analyses/{analysis_id}/frames", response_model=FramesPayload,
             responses=ERRORS)
    def get_frames(analysis_id: str, user: User = signed_in) -> Response:
        """Per-frame landmarks and metric series.

        Served straight from the pipeline's frames.json (validated against
        FramesPayload in tests) to avoid re-parsing a large payload per request.
        """
        row, sharer = readable_row(analysis_id, user)
        if sharer is None and row["status"] != "succeeded":
            raise HTTPException(status.HTTP_409_CONFLICT, f"Analysis is {row['status']}")
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

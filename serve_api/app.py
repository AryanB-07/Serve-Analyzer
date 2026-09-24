"""FastAPI application. Run with: uvicorn serve_api.app:create_app --factory --reload"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse

from . import keys
from .convert import result_from_file, summary_from_row
from .db import Database
from .schemas import (
    AnalysisList,
    AnalysisResult,
    AnalysisSummary,
    CreateAnalysisRequest,
    CreateAnalysisResponse,
    ErrorResponse,
    FramesPayload,
    UploadTarget,
)
from .settings import Settings
from .storage import LocalStorage, StorageError

IMMUTABLE = "private, max-age=31536000, immutable"
ERRORS = {404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}}


def _encode_cursor(row: dict) -> str:
    return base64.urlsafe_b64encode(f"{row['created_at']}|{row['id']}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        created_at, analysis_id = base64.urlsafe_b64decode(cursor).decode().split("|")
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid cursor") from exc
    return created_at, analysis_id


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    db = Database(settings.db_path)
    storage = LocalStorage(settings)

    app = FastAPI(title="Serve Analyzer API", version="1.0.0")
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    def get_row(analysis_id: str) -> dict:
        row = db.get(analysis_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
        return row

    def signed_get(key: str) -> str:
        return storage.presign("GET", key)[0]

    def succeeded_row(analysis_id: str) -> dict:
        row = get_row(analysis_id)
        if row["status"] != "succeeded":
            raise HTTPException(status.HTTP_409_CONFLICT, f"Analysis is {row['status']}")
        return row

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/analyses", status_code=201, response_model=CreateAnalysisResponse,
              responses={413: {"model": ErrorResponse}})
    def create_analysis(body: CreateAnalysisRequest) -> CreateAnalysisResponse:
        """Create a record and return a presigned URL to PUT the video to."""
        if body.size_bytes > settings.max_upload_bytes:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                f"Videos must be under {settings.max_upload_bytes // (1024 * 1024)} MB",
            )
        row = db.create(body.hand, body.filename, body.content_type, body.size_bytes)
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

    @app.get("/analyses", response_model=AnalysisList)
    def list_analyses(
        limit: Annotated[int, Query(ge=1, le=100)] = 20, cursor: str | None = None
    ) -> AnalysisList:
        rows = db.list(limit + 1, _decode_cursor(cursor) if cursor else None)
        page = rows[:limit]
        return AnalysisList(
            items=[summary_from_row(r, signed_get) for r in page],
            next_cursor=_encode_cursor(page[-1]) if len(rows) > limit else None,
        )

    @app.get("/analyses/{analysis_id}", response_model=AnalysisSummary, responses=ERRORS)
    def get_analysis(analysis_id: str) -> AnalysisSummary:
        return summary_from_row(get_row(analysis_id), signed_get)

    @app.post("/analyses/{analysis_id}/start", status_code=202, response_model=AnalysisSummary,
              responses=ERRORS)
    def start_analysis(analysis_id: str) -> AnalysisSummary:
        """Queue the analysis once the upload has finished."""
        row = get_row(analysis_id)
        if not storage.exists(keys.input_key(analysis_id, row["content_type"])):
            raise HTTPException(status.HTTP_409_CONFLICT, "The video has not been uploaded yet")
        if not db.transition(analysis_id, ("awaiting_upload",), "queued"):
            raise HTTPException(status.HTTP_409_CONFLICT, f"Analysis is already {row['status']}")
        return summary_from_row(get_row(analysis_id), signed_get)

    @app.post("/analyses/{analysis_id}/retry", status_code=202, response_model=AnalysisSummary,
              responses=ERRORS)
    def retry_analysis(analysis_id: str) -> AnalysisSummary:
        row = get_row(analysis_id)
        if not db.transition(analysis_id, ("failed",), "queued"):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Only failed analyses can be retried; this one is {row['status']}",
            )
        return summary_from_row(get_row(analysis_id), signed_get)

    @app.get("/analyses/{analysis_id}/result", response_model=AnalysisResult, responses=ERRORS)
    def get_result(analysis_id: str) -> AnalysisResult:
        succeeded_row(analysis_id)
        results = json.loads(storage.path(keys.output_key(analysis_id, keys.RESULTS)).read_text())
        return result_from_file(analysis_id, results, signed_get)

    @app.get("/analyses/{analysis_id}/frames", response_model=FramesPayload,
             responses=ERRORS)
    def get_frames(analysis_id: str) -> Response:
        """Per-frame landmarks and metric series.

        Served straight from the pipeline's frames.json (validated against
        FramesPayload in tests) to avoid re-parsing a large payload per request.
        """
        succeeded_row(analysis_id)
        path = storage.path(keys.output_key(analysis_id, keys.FRAMES))
        return Response(
            path.read_bytes(), media_type="application/json",
            headers={"Cache-Control": IMMUTABLE},
        )

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

    return app

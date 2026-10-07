"""Object-storage key layout, shared by the API and the worker."""

from __future__ import annotations

from serve_analyzer import outputs

EXTENSIONS = {"video/mp4": ".mp4", "video/quicktime": ".mov"}


def upload_prefix(analysis_id: str) -> str:
    return f"uploads/{analysis_id}"


def input_key(analysis_id: str, content_type: str) -> str:
    return f"{upload_prefix(analysis_id)}/input{EXTENSIONS[content_type]}"


def output_prefix(analysis_id: str) -> str:
    return f"analyses/{analysis_id}"


def output_key(analysis_id: str, filename: str) -> str:
    return f"{output_prefix(analysis_id)}/{filename}"


RESULTS = outputs.RESULTS_FILE
FRAMES = outputs.FRAMES_FILE
PLAYBACK = outputs.PLAYBACK_FILE
ANNOTATED = outputs.ANNOTATED_FILE
THUMBNAIL = outputs.THUMBNAIL_FILE

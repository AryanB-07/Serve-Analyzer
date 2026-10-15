"""Object-storage key layout, shared by the API and the worker."""

from __future__ import annotations

from serve_analyzer import outputs

EXTENSIONS = {
    "video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm",
    "video/x-matroska": ".mkv", "video/x-msvideo": ".avi", "video/3gpp": ".3gp",
    "video/mp2t": ".mts",
}


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


def avatar_prefix(user_id: str) -> str:
    """Everything stored for an account's profile picture."""
    return f"avatars/{user_id}"


def avatar_key(user_id: str, version: str) -> str:
    """A new key per picture, so a replaced one is never served from a cache."""
    return f"{avatar_prefix(user_id)}/{version}/{AVATAR}"


AVATAR = "avatar.jpg"


def post_prefix(post_id: str) -> str:
    """A post's own copy of its serve: the skeleton video and the thumbnail."""
    return f"posts/{post_id}"


POST_VIDEO = "video.mp4"
POST_THUMBNAIL = "thumbnail.jpg"

"""Pipeline exceptions with stable, machine-readable codes."""

from __future__ import annotations

from typing import Literal

ErrorCode = Literal[
    "UNREADABLE_VIDEO",
    "VIDEO_TOO_LONG",
    "FPS_TOO_LOW",
    "NO_PERSON_DETECTED",
    "INTERNAL",
]


class PipelineError(Exception):
    code: ErrorCode = "INTERNAL"

    def __init__(self, message: str, code: ErrorCode | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class VideoValidationError(PipelineError, ValueError):
    """The input video cannot be analysed (unreadable, too long, too slow)."""

    code: ErrorCode = "UNREADABLE_VIDEO"


class AnalysisError(PipelineError):
    """The video was valid but could not be analysed (e.g. no person found)."""

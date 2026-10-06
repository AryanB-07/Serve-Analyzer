"""API request/response models. The frontend's TypeScript types are generated from these."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, create_model, field_validator

from serve_analyzer.angles import METRIC_NAMES
from serve_analyzer.errors import ErrorCode
from serve_analyzer.landmarks import DRAWN_LANDMARKS
from serve_analyzer.metrics import PHASE_NAMES

Hand = Literal["right", "left"]
AnalysisStatus = Literal[
    "awaiting_upload", "queued", "extracting_pose", "analyzing", "rendering", "succeeded", "failed"
]
MetricStatus = Literal["good", "borderline", "off", "unknown"]
PhaseName = Literal["trophy", "racket_drop", "contact"]
MetricName = Literal[
    "front_knee_flexion", "back_knee_flexion", "elbow_angle", "trunk_tilt", "wrist_height"
]
UploadContentType = Literal["video/mp4", "video/quicktime"]


def _keyed(name: str, keys: list[str], value_type: Any, default: Any = ...) -> type[BaseModel]:
    """A model with one field per key, so generated TS types keep the key names."""
    return create_model(name, **{k: (value_type, default) for k in keys})


class ApiError(BaseModel):
    code: ErrorCode
    message: str


class StatusCounts(BaseModel):
    good: int
    borderline: int
    off: int
    unknown: int


class AnalysisSummary(BaseModel):
    id: str
    hand: Hand
    status: AnalysisStatus
    filename: str
    created_at: datetime
    updated_at: datetime
    error: ApiError | None = None
    thumbnail_url: str | None = None
    counts: StatusCounts | None = None


class AnalysisList(BaseModel):
    items: list[AnalysisSummary]
    next_cursor: str | None = None


class CreateAnalysisRequest(BaseModel):
    hand: Hand
    filename: str = Field(min_length=1, max_length=255)
    content_type: UploadContentType
    size_bytes: int = Field(gt=0)


class UploadTarget(BaseModel):
    url: str
    method: Literal["PUT"] = "PUT"
    headers: dict[str, str]
    expires_at: datetime


class CreateAnalysisResponse(BaseModel):
    analysis: AnalysisSummary
    upload: UploadTarget


class PhaseFrames(BaseModel):
    trophy: int | None
    racket_drop: int | None
    contact: int | None


class MetricRange(BaseModel):
    good: tuple[float, float]
    borderline: tuple[float, float]


MetricValues = _keyed("MetricValues", METRIC_NAMES, float | None)
MetricLabels = _keyed("MetricLabels", METRIC_NAMES, MetricStatus | None, None)
MetricRanges = _keyed("MetricRanges", METRIC_NAMES, MetricRange | None, None)
PhaseMetrics = _keyed("PhaseMetrics", PHASE_NAMES, MetricValues)
PhaseLabels = _keyed("PhaseLabels", PHASE_NAMES, MetricLabels)
PhaseRanges = _keyed("PhaseRanges", PHASE_NAMES, MetricRanges)


class FeedbackItem(BaseModel):
    text: str
    phase: PhaseName | None = None
    metric: MetricName | None = None
    status: MetricStatus | None = None


class AnalysisResult(BaseModel):
    id: str
    hand: Hand
    fps: float
    n_frames: int
    width: int
    height: int
    phases: PhaseFrames
    metrics: PhaseMetrics
    labels: PhaseLabels
    ranges: PhaseRanges
    feedback: list[FeedbackItem]
    warnings: list[str]
    video_url: str
    annotated_video_url: str | None = None
    thumbnail_url: str | None = None


Series = list[float | None]


class LandmarkTrack(BaseModel):
    """Normalised coordinates (0-1 of the frame), one entry per frame; null when missing."""

    x: Series
    y: Series


class RawLandmarkTrack(LandmarkTrack):
    v: Series


LANDMARK_NAMES = list(DRAWN_LANDMARKS)
RawLandmarks = _keyed("RawLandmarks", LANDMARK_NAMES, RawLandmarkTrack)
SmoothedLandmarks = _keyed("SmoothedLandmarks", LANDMARK_NAMES, LandmarkTrack)
MetricSeries = _keyed("MetricSeries", METRIC_NAMES, Series)


class FrameLandmarks(BaseModel):
    raw: RawLandmarks
    smoothed: SmoothedLandmarks


class FramesPayload(BaseModel):
    fps: float
    n_frames: int
    width: int
    height: int
    phases: PhaseFrames
    landmarks: FrameLandmarks
    series: MetricSeries


class ErrorResponse(BaseModel):
    detail: str


MIN_PASSWORD_LENGTH = 8


class SignupRequest(BaseModel):
    email: EmailStr = Field(max_length=320)
    # No composition rules (NIST SP 800-63B); the upper bound caps hashing cost.
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)
    # The person confirms they're old enough and agree to the Terms and Privacy Policy.
    accept_terms: bool

    @field_validator("accept_terms")
    @classmethod
    def _must_accept(cls, value: bool) -> bool:
        if not value:
            raise ValueError("You need to accept the Terms of Service and Privacy Policy.")
        return value


class LoginRequest(BaseModel):
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=1, max_length=256)


class User(BaseModel):
    id: str
    email: str
    created_at: datetime
    email_verified: bool = False


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1, max_length=128)


class PasswordResetRequest(BaseModel):
    email: EmailStr = Field(max_length=320)


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)


class DeleteAccountRequest(BaseModel):
    """The current password, so a borrowed or stolen session can't delete the account."""

    password: str = Field(min_length=1, max_length=256)

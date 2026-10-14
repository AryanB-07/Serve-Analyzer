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
# One canonical type per container; the frontend picks it from the file extension (browsers
# report these inconsistently). The pipeline also converts other codecs, such as AV1, with ffmpeg.
# Where the camera was, relative to the hitting arm (serve_analyzer.view.CAMERA_VIEWS). Optional:
# people are asked at upload, because guessing it from the skeleton wasn't reliable enough.
CameraView = Literal[
    "side_hitting", "side_toss", "behind", "behind_diagonal_hitting", "behind_diagonal_toss",
    "front", "front_diagonal_hitting", "front_diagonal_toss",
]
MeasurementQuality = Literal["measured", "approximate", "unreadable"]
UploadContentType = Literal[
    "video/mp4", "video/quicktime", "video/webm", "video/x-matroska", "video/x-msvideo",
    "video/3gpp", "video/mp2t",
]


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
    camera_view: CameraView | None = None


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
MetricQualities = _keyed("MetricQualities", METRIC_NAMES, MeasurementQuality | None, None)
PhaseQualities = _keyed("PhaseQualities", PHASE_NAMES, MetricQualities, None)


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
    camera_view: CameraView | None = None
    # What camera_view can read, per phase and measurement; None when it wasn't given.
    quality: PhaseQualities | None = None
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


class ChangeEmailRequest(BaseModel):
    """The current password too, so a borrowed or stolen session can't take over the account."""

    new_email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=1, max_length=256)


class ConfirmEmailChangeRequest(BaseModel):
    token: str = Field(min_length=1, max_length=128)


# "This result looks wrong". The first five are for a finished analysis, the last for one
# rejected as not a serve; "other" fits either.
ReportReason = Literal[
    "not_a_serve", "wrong_phases", "wrong_tracking", "wrong_feedback", "was_a_serve", "other",
]
SUCCEEDED_REASONS = ("not_a_serve", "wrong_phases", "wrong_tracking", "wrong_feedback", "other")
FAILED_REASONS = ("was_a_serve", "other")
MAX_NOTE_LENGTH = 1000


class ReportRequest(BaseModel):
    reason: ReportReason
    note: str | None = Field(default=None, max_length=MAX_NOTE_LENGTH)


class Report(BaseModel):
    reason: ReportReason
    note: str | None = None
    created_at: datetime


class ExportedAccount(BaseModel):
    email: str
    email_verified: bool
    created_at: datetime
    terms_version: str | None = None
    terms_accepted_at: datetime | None = None


class ExportedAnalysis(BaseModel):
    id: str
    filename: str
    hand: Hand
    status: AnalysisStatus
    created_at: datetime
    error: ApiError | None = None
    camera_view: CameraView | None = None
    original_video_deleted_at: datetime | None = None
    # The pipeline's results.json: phases, angles, labels, ranges, feedback and warnings.
    results: dict[str, Any] | None = None
    report: Report | None = None
    # Download links for the stored files (videos, per-frame data), valid for a few hours.
    files: dict[str, str] = {}


class DataExport(BaseModel):
    """Everything stored about an account, as given by "Download my data"."""

    exported_at: datetime
    links_expire_at: datetime
    account: ExportedAccount
    analyses: list[ExportedAnalysis]

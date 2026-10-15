"""API request/response models. The frontend's TypeScript types are generated from these."""

from __future__ import annotations

import re
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


KeyPosition = Literal["front_knee_flexion", "back_knee_flexion", "trunk_tilt", "elbow_angle", "wrist_height"]
ScoreBand = Literal["good", "borderline", "off"]


class KeyScore(BaseModel):
    """One key position's score, for History's cards (serve_analyzer.score)."""

    phase: PhaseName
    value: float
    score: int = Field(ge=0, le=100)
    band: ScoreBand


KeyScores = _keyed("KeyScores", ["front_knee_flexion", "back_knee_flexion", "trunk_tilt", "elbow_angle", "wrist_height"],
                   KeyScore | None, None)
MAX_ANALYSIS_NOTE = 1000


class NoteRequest(BaseModel):
    """The person's own note on an analysis; empty or null clears it."""

    note: str | None = Field(default=None, max_length=MAX_ANALYSIS_NOTE)


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
    # 0-100, as in simple mode; null until it succeeds (or if nothing could be scored).
    overall_score: int | None = Field(default=None, ge=0, le=100)
    key_scores: KeyScores | None = None
    note: str | None = None


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


class MeasurementConfidence(BaseModel):
    """How far one measurement can be trusted (serve_analyzer.confidence)."""

    visibility: float | None = None    # 0-1: MediaPipe's confidence in the weakest joint it uses
    noise: float | None = None         # frame-to-frame tracking jitter (degrees; body heights for height)
    camera_error: float | None = None  # the rig's 90th-percentile error for the camera position
    camera_view_assumed: bool = False  # true: no position was given, so side-on (hitting side) is assumed


MetricValues = _keyed("MetricValues", METRIC_NAMES, float | None)
MetricLabels = _keyed("MetricLabels", METRIC_NAMES, MetricStatus | None, None)
MetricRanges = _keyed("MetricRanges", METRIC_NAMES, MetricRange | None, None)
PhaseMetrics = _keyed("PhaseMetrics", PHASE_NAMES, MetricValues)
PhaseLabels = _keyed("PhaseLabels", PHASE_NAMES, MetricLabels)
PhaseRanges = _keyed("PhaseRanges", PHASE_NAMES, MetricRanges)
MetricQualities = _keyed("MetricQualities", METRIC_NAMES, MeasurementQuality | None, None)
MetricConfidences = _keyed("MetricConfidences", METRIC_NAMES, MeasurementConfidence | None, None)
# A phase that wasn't detected has no entry, sent as null.
PhaseQualities = _keyed("PhaseQualities", PHASE_NAMES, MetricQualities | None, None)
PhaseConfidences = _keyed("PhaseConfidences", PHASE_NAMES, MetricConfidences | None, None)


class FeedbackItem(BaseModel):
    text: str
    phase: PhaseName | None = None
    metric: MetricName | None = None
    status: MetricStatus | None = None
    # The same point without numbers, for simple mode (absent from results before it existed).
    plain: str | None = None



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
    # How far each measurement can be trusted; None for results from before it existed.
    confidence: PhaseConfidences | None = None
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
    note: str | None = None
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
    profile: ExportedProfile | None = None
    analyses: list[ExportedAnalysis]
    connections: list[ExportedConnection] = []
    blocks: list[ExportedBlock] = []
    conversations: list[ExportedConversation] = []
    reports_made: list[ExportedUserReport] = []


# --- profiles ---------------------------------------------------------------------------------

USERNAME_PATTERN = r"^[a-z0-9_]{3,20}$"
MAX_DISPLAY_NAME = 50
MAX_BIO = 300
# Names that would look official, or clash with pages, once usernames are public.
RESERVED_USERNAMES = frozenset({
    "admin", "administrator", "api", "app", "help", "me", "mod", "moderator", "null", "privacy",
    "profile", "root", "serve", "serveanalyzer", "serve_analyzer", "settings", "staff", "support",
    "system", "terms", "undefined", "user", "users",
})
_CONTROL = {chr(c) for c in range(32)} | {chr(127)}


def normalise_username(value: str) -> str:
    return value.strip().lstrip("@").lower()


def username_problem(username: str) -> str | None:
    """Why ``username`` (already normalised) can't be used, or None."""
    if not 3 <= len(username) <= 20:
        return "Usernames are 3 to 20 characters."
    if not re.fullmatch(USERNAME_PATTERN, username):
        return "Use only letters, numbers and underscores."
    if username in RESERVED_USERNAMES:
        return "That username is reserved."
    return None


def _clean_text(value: str | None, keep_newlines: bool) -> str | None:
    """Trimmed, without control characters (newlines kept in a bio); empty means none."""
    if value is None:
        return None
    allowed = {"\n"} if keep_newlines else set()
    cleaned = "".join(ch for ch in value.replace("\r\n", "\n") if ch not in _CONTROL or ch in allowed)
    if not keep_newlines:
        cleaned = " ".join(cleaned.split())
    cleaned = cleaned.strip()
    return cleaned or None


class ProfileStats(BaseModel):
    serves: int  # finished analyses
    average_score: int | None = None  # of the latest `averaged_over` scored serves
    averaged_over: int = 0
    best_score: int | None = None


class SharingSettings(BaseModel):
    """What friends may see of your serves. All off until you turn them on."""

    share_stats: bool = False  # serves analysed, average, best, trend
    share_positions: bool = False  # each key position's average
    on_leaderboard: bool = False  # a place on your friends' leaderboard


class Profile(SharingSettings):
    username: str | None = None
    display_name: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    member_since: datetime
    stats: ProfileStats
    accept_requests: bool = True  # whether anyone with your username can send a friend request


class ProfileUpdate(BaseModel):
    """Only the fields sent are changed. An empty display name or bio removes it; a username,
    once chosen, can be changed but not removed."""

    username: str | None = Field(default=None, max_length=40)
    display_name: str | None = Field(default=None, max_length=200)
    bio: str | None = Field(default=None, max_length=1000)
    accept_requests: bool | None = None
    share_stats: bool | None = None
    share_positions: bool | None = None
    on_leaderboard: bool | None = None

    @field_validator("accept_requests", "share_stats", "share_positions", "on_leaderboard")
    @classmethod
    def _switch(cls, value: bool | None) -> bool:
        if value is None:
            raise ValueError("Settings are on or off.")
        return value

    @field_validator("username")
    @classmethod
    def _username(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("A username can be changed but not removed.")
        username = normalise_username(value)
        if problem := username_problem(username):
            raise ValueError(problem)
        return username

    @field_validator("display_name")
    @classmethod
    def _display_name(cls, value: str | None) -> str | None:
        cleaned = _clean_text(value, keep_newlines=False)
        if cleaned and len(cleaned) > MAX_DISPLAY_NAME:
            raise ValueError(f"Names are up to {MAX_DISPLAY_NAME} characters.")
        return cleaned

    @field_validator("bio")
    @classmethod
    def _bio(cls, value: str | None) -> str | None:
        cleaned = _clean_text(value, keep_newlines=True)
        if cleaned and len(cleaned) > MAX_BIO:
            raise ValueError(f"Bios are up to {MAX_BIO} characters.")
        return cleaned


class UsernameCheck(BaseModel):
    username: str  # as it would be saved
    available: bool
    problem: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)


# --- friends ----------------------------------------------------------------------------------

Relationship = Literal["self", "none", "requested", "incoming", "friends"]


class PersonSummary(BaseModel):
    """What anyone who can see you is shown: never an email or anything private."""

    username: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None


class TrendPoint(BaseModel):
    at: datetime
    score: int = Field(ge=0, le=100)


class PositionAverage(BaseModel):
    score: int = Field(ge=0, le=100)
    measured: int  # how many of the latest serves it was measured in


SharedPositions = _keyed("SharedPositions", ["front_knee_flexion", "back_knee_flexion", "trunk_tilt", "elbow_angle",
                                             "wrist_height"], PositionAverage | None, None)


class SharedStats(BaseModel):
    serves: int
    average_score: int | None = None  # of the latest `averaged_over` scored serves
    averaged_over: int = 0
    best_score: int | None = None
    trend: list[TrendPoint] = []  # the latest scored serves, oldest first
    change: int | None = None  # the latest five's average minus the five before's


class Person(PersonSummary):
    """Someone's page, as you see it."""

    relationship: Relationship
    connection_id: str | None = None  # the request or friendship, when there is one
    can_request: bool = False  # whether you could send them a friend request now
    bio: str | None = None  # friends only
    friends_since: datetime | None = None
    # Friends only, and only what they chose to share (None when they don't).
    stats: SharedStats | None = None
    positions: SharedPositions | None = None  # type: ignore[valid-type]


class LeaderboardEntry(BaseModel):
    rank: int | None = None  # None until they have enough serves
    person: PersonSummary
    is_you: bool = False
    average_score: int | None = None
    scored_serves: int  # within the window
    needed: int = 0  # more serves before they're ranked


class Leaderboard(BaseModel):
    window_days: int
    min_serves: int
    averaged_over: int
    you_are_on_it: bool
    ranked: list[LeaderboardEntry]
    not_ranked: list[LeaderboardEntry]


class Connection(BaseModel):
    id: str
    person: PersonSummary  # the other person
    status: Literal["pending", "accepted"]
    direction: Literal["incoming", "outgoing"]  # who asked: them, or you
    created_at: datetime
    accepted_at: datetime | None = None


class ConnectionList(BaseModel):
    friends: list[Connection]
    incoming: list[Connection]
    outgoing: list[Connection]


class RequestCount(BaseModel):
    incoming: int


class UsernameRequest(BaseModel):
    username: str = Field(min_length=1, max_length=40)


class BlockedPerson(BaseModel):
    person: PersonSummary
    blocked_at: datetime


# --- messages ---------------------------------------------------------------------------------

MAX_MESSAGE = 2000
ReportReason = Literal["spam", "harassment", "inappropriate", "impersonation", "other"]


class Message(BaseModel):
    id: str
    from_you: bool
    body: str | None = None  # None once deleted
    deleted: bool = False
    created_at: datetime


class MessagePreview(BaseModel):
    text: str | None = None  # the start of the message; None if it was deleted
    from_you: bool
    deleted: bool = False
    at: datetime


class ConversationSummary(BaseModel):
    id: str
    person: PersonSummary | None = None  # None when they've deleted their account
    last_message: MessagePreview | None = None
    unread: int = 0
    can_send: bool  # only while you're friends
    why_not: str | None = None  # when you can't send, why


class MessagePage(BaseModel):
    items: list[Message]  # newest first
    next_cursor: str | None = None
    seen_up_to: datetime | None = None  # the other person has read everything up to here


class StartConversation(BaseModel):
    username: str = Field(min_length=1, max_length=40)


class SendMessage(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_MESSAGE * 2)

    @field_validator("body")
    @classmethod
    def _body(cls, value: str) -> str:
        cleaned = "".join(ch for ch in value.replace("\r\n", "\n") if ch not in _CONTROL or ch in "\n\t").strip()
        if not cleaned:
            raise ValueError("Write a message first.")
        if len(cleaned) > MAX_MESSAGE:
            raise ValueError(f"Messages are up to {MAX_MESSAGE:,} characters.")
        return cleaned


class UnreadCount(BaseModel):
    unread: int


class UserReportRequest(BaseModel):
    username: str = Field(min_length=1, max_length=40)
    message_id: str | None = Field(default=None, max_length=32)
    reason: ReportReason
    note: str | None = Field(default=None, max_length=1000)


class ExportedMessage(BaseModel):
    from_you: bool
    body: str | None = None
    deleted: bool = False
    created_at: datetime


class ExportedConversation(BaseModel):
    with_username: str | None = None  # None if they deleted their account
    messages: list[ExportedMessage]


class ExportedUserReport(BaseModel):
    username: str | None = None
    reason: ReportReason
    note: str | None = None
    message: str | None = None
    created_at: datetime


class ExportedConnection(BaseModel):
    username: str | None = None
    status: Literal["pending", "accepted"]
    direction: Literal["incoming", "outgoing"]
    created_at: datetime
    accepted_at: datetime | None = None


class ExportedBlock(BaseModel):
    username: str | None = None
    blocked_at: datetime


class ExportedProfile(SharingSettings):
    accept_requests: bool = True
    username: str | None = None
    display_name: str | None = None
    bio: str | None = None
    avatar: str | None = None  # a download link, like the videos

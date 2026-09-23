"""Core data structures passed between pipeline stages."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np


class Hand(str, Enum):
    RIGHT = "right"
    LEFT = "left"


@dataclass
class VideoInfo:
    path: Path
    fps: float
    frame_count: int
    width: int
    height: int

    @property
    def duration_s(self) -> float:
        return self.frame_count / self.fps


@dataclass
class PoseSequence:
    """Per-frame landmarks in pixel coordinates.

    ``landmarks`` has shape (frames, 33, 3) holding [x, y, visibility].
    Missing or low-confidence points are NaN in x and y.
    """

    landmarks: np.ndarray
    fps: float
    width: int
    height: int

    @property
    def n_frames(self) -> int:
        return self.landmarks.shape[0]

    def xy(self, index: int) -> np.ndarray:
        """(frames, 2) trajectory of one landmark."""
        return self.landmarks[:, index, :2]


@dataclass
class PhaseFrames:
    trophy: int | None = None
    racket_drop: int | None = None
    contact: int | None = None

    def as_dict(self) -> dict[str, int | None]:
        return asdict(self)


Metrics = dict[str, dict[str, float | None]]
Labels = dict[str, dict[str, str]]
Ranges = dict[str, dict[str, dict[str, list[float]]]]

RESULTS_SCHEMA_VERSION = 2


@dataclass
class FeedbackItem:
    """One coaching point. ``phase``/``metric`` link it to the moment it is about."""

    text: str
    phase: str | None = None
    metric: str | None = None
    status: str | None = None


@dataclass
class AnalysisResult:
    hand: Hand
    fps: float
    n_frames: int
    width: int
    height: int
    phases: PhaseFrames
    metrics: Metrics
    labels: Labels
    ranges: Ranges
    feedback: list[FeedbackItem]
    warnings: list[str] = field(default_factory=list)
    outputs: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": RESULTS_SCHEMA_VERSION,
            "hand": self.hand.value,
            "fps": self.fps,
            "n_frames": self.n_frames,
            "width": self.width,
            "height": self.height,
            "phases": self.phases.as_dict(),
            "metrics": self.metrics,
            "labels": self.labels,
            "ranges": self.ranges,
            "feedback": [asdict(f) for f in self.feedback],
            "warnings": self.warnings,
            "outputs": self.outputs,
        }

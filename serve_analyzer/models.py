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


@dataclass
class AnalysisResult:
    hand: Hand
    fps: float
    n_frames: int
    phases: PhaseFrames
    metrics: Metrics
    labels: Labels
    feedback: list[str]
    outputs: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hand": self.hand.value,
            "fps": self.fps,
            "n_frames": self.n_frames,
            "phases": self.phases.as_dict(),
            "metrics": self.metrics,
            "labels": self.labels,
            "feedback": self.feedback,
            "outputs": self.outputs,
        }

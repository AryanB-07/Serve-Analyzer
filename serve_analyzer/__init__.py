"""Serve Analyzer: tennis serve technique analysis from a side-on video."""

from typing import TYPE_CHECKING

from .config import AnalysisConfig
from .models import AnalysisResult, Hand, PhaseFrames, PoseSequence

if TYPE_CHECKING:
    from .pipeline import analyze

__all__ = ["AnalysisConfig", "AnalysisResult", "Hand", "PhaseFrames", "PoseSequence", "analyze"]


def __getattr__(name: str):
    # The pipeline loads MediaPipe and OpenCV (about 200 MB), so it's imported only when used.
    # The API imports this package for its schemas and must not pay for that.
    if name == "analyze":
        from .pipeline import analyze

        return analyze
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

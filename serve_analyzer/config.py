"""Tunable parameters for the pipeline, with sensible defaults."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class AnalysisConfig:
    max_duration_s: float = 15.0
    min_fps: float = 24.0

    model_variant: str = "heavy"  # lite | full | heavy
    model_dir: Path = Path.home() / ".cache" / "serve_analyzer"

    visibility_threshold: float = 0.5
    max_gap_frames: int = 5

    smoothing_enabled: bool = True
    smoothing_window_ms: float = 150.0
    smoothing_polyorder: int = 2

    reference_ranges_path: Path | None = None

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

    # Multi-view options; see docs/tuning-results.md for the experiments behind each default.
    angle_space: str = "image2d"          # image2d | world3d (world3d: experimental)
    trophy_method: str = "knee_toss"      # knee_toss | toss_peak
    racket_drop_method: str = "min_elbow"  # min_elbow | wrist_low
    require_complete_serve: bool = True
    phase_signal_space: str = "image2d"   # image2d | angle_space: which series times the phases
    contact_visibility_threshold: float | None = 0.1  # None = use visibility_threshold
    trophy_window_s: float | None = 0.8   # only consider trophy frames this close before contact
    trophy_fallback: bool = False         # use the toss-hand peak when knees can't be measured
    trophy_plateau_deg: float | None = None  # centre of the near-peak knee plateau instead of the argmax

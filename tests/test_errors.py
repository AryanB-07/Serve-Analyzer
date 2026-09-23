from pathlib import Path

import numpy as np
import pytest

from serve_analyzer.config import AnalysisConfig
from serve_analyzer.errors import AnalysisError, VideoValidationError
from serve_analyzer.models import Hand, PoseSequence, VideoInfo
from serve_analyzer.pipeline import analyze_sequence
from serve_analyzer.reference import load_ranges
from serve_analyzer.video import probe, validate


def _info(fps: float, frames: int) -> VideoInfo:
    return VideoInfo(Path("x.mp4"), fps, frames, 640, 480)


def test_validation_errors_carry_codes():
    with pytest.raises(VideoValidationError) as long:
        validate(_info(30, 30 * 16), max_duration_s=15, min_fps=24)
    assert long.value.code == "VIDEO_TOO_LONG"
    with pytest.raises(VideoValidationError) as slow:
        validate(_info(15, 30), max_duration_s=15, min_fps=24)
    assert slow.value.code == "FPS_TOO_LOW"


def test_missing_file_is_unreadable(tmp_path):
    with pytest.raises(VideoValidationError) as exc:
        probe(tmp_path / "nope.mp4")
    assert exc.value.code == "UNREADABLE_VIDEO"


def test_no_person_detected():
    lm = np.full((10, 33, 3), np.nan)
    lm[..., 2] = 0.0
    with pytest.raises(AnalysisError) as exc:
        analyze_sequence(PoseSequence(lm, 30.0, 640, 480), Hand.RIGHT, AnalysisConfig(), load_ranges())
    assert exc.value.code == "NO_PERSON_DETECTED"

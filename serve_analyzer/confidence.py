"""How far each measurement can be trusted: the numbers behind the results page's advanced mode.

For each measurement at its phase:

- ``visibility``: how sure MediaPipe was of the joints it uses, 0-1. The weakest joint counts,
  because one hidden ankle spoils a knee angle. Taken as each joint's median over the five
  frames around the phase.
- ``noise``: how far the raw frame-by-frame angle wobbles around the smoothed one there (root
  mean square over seven frames), in degrees (body heights for wrist height). This is tracking
  jitter, not error in the camera's view.
- ``camera_error``: the synthetic rig's 90th-percentile error for the camera position
  (data/view_reliability.json). When nobody said where the camera was, it's the error from
  side-on on the hitting-arm side, the filming guide's position, and ``camera_view_assumed`` is
  true. This is usually the bigger number: a single camera can't see bends toward or away from it.
"""

from __future__ import annotations

import numpy as np

from . import angles as A
from . import landmarks as L
from .config import AnalysisConfig
from .models import Hand, PhaseFrames, PoseSequence
from .preprocessing import clean
from .view import _reliability_table

GUIDE_VIEW = "side_hitting"
VIS_HALF_WINDOW = 2
NOISE_HALF_WINDOW = 3


def _joint_groups(metric: str, hand: Hand) -> list[list[int]]:
    """Landmarks each measurement needs, as groups: every group is needed, any joint in a group will do."""
    arm, front, back = L.hitting_arm(hand), L.front_leg(hand), L.back_leg(hand)
    return {
        A.FRONT_KNEE_FLEXION: [[front.hip], [front.knee], [front.ankle]],
        A.BACK_KNEE_FLEXION: [[back.hip], [back.knee], [back.ankle]],
        A.ELBOW_ANGLE: [[arm.shoulder], [arm.elbow], [arm.wrist]],
        A.TRUNK_TILT: [[L.LEFT_SHOULDER], [L.RIGHT_SHOULDER], [L.LEFT_HIP], [L.RIGHT_HIP]],
        # Height is measured from the lower ankle, so either ankle will do.
        A.WRIST_HEIGHT: [[arm.wrist], [L.NOSE], [L.LEFT_ANKLE, L.RIGHT_ANKLE]],
    }[metric]


def _visibility(raw: PoseSequence, frame: int, groups: list[list[int]]) -> float | None:
    window = raw.landmarks[max(0, frame - VIS_HALF_WINDOW):frame + VIS_HALF_WINDOW + 1, :, 2]
    if window.size == 0:
        return None
    best_in_group = [max(float(np.nanmedian(window[:, j])) for j in group) for group in groups]
    value = min(best_in_group)
    return None if np.isnan(value) else value


def _noise(raw_series: np.ndarray, smooth_series: np.ndarray, frame: int) -> float | None:
    lo, hi = max(0, frame - NOISE_HALF_WINDOW), frame + NOISE_HALF_WINDOW + 1
    diff = raw_series[lo:hi] - smooth_series[lo:hi]
    diff = diff[np.isfinite(diff)]
    if len(diff) < 3:
        return None
    return float(np.sqrt(np.mean(diff ** 2)))


def measurement_confidence(
    raw: PoseSequence, series: A.Series, phases: PhaseFrames, hand: Hand, config: AnalysisConfig,
    measured: dict[str, list[str]], camera_view: str | None,
) -> dict[str, dict[str, dict]]:
    """{phase: {metric: {visibility, noise, camera_error, camera_view_assumed}}} for the
    ``measured`` measurements ({phase: [metric, ...]}) whose phase was found."""
    unsmoothed = clean(raw, config.visibility_threshold, config.max_gap_frames, None)
    raw_series = A.compute_series(unsmoothed, hand, config.angle_space)
    errors = _reliability_table()[camera_view or GUIDE_VIEW]
    out: dict[str, dict[str, dict]] = {}
    for phase, metrics in measured.items():
        frame = getattr(phases, phase)
        if frame is None:
            continue
        for metric in metrics:
            visibility = _visibility(raw, frame, _joint_groups(metric, hand))
            noise = _noise(raw_series[metric], series[metric], frame)
            height = metric == A.WRIST_HEIGHT
            error = errors.get(f"{phase}.{metric}")
            out.setdefault(phase, {})[metric] = {
                "visibility": None if visibility is None else round(visibility, 2),
                "noise": None if noise is None else round(noise, 3 if height else 1),
                "camera_error": None if error is None else round(error, 3 if height else 1),
                "camera_view_assumed": camera_view is None,
            }
    return out

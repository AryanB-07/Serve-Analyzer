"""Heuristic serve phase detection.

Each detector takes per-frame arrays and returns a frame index, or None if
the phase cannot be found. They are kept separate so any one can later be
replaced by a learned classifier with the same signature.
"""

from __future__ import annotations

import warnings

import numpy as np

from . import angles as A
from .models import PhaseFrames


def _nanargmax_in(values: np.ndarray, mask: np.ndarray) -> int | None:
    candidates = np.where(mask & ~np.isnan(values), values, -np.inf)
    if not np.isfinite(candidates).any():
        return None
    return int(np.argmax(candidates))


def detect_contact(wrist_elevation: np.ndarray) -> int | None:
    """Contact: the frame where the hitting wrist is highest."""
    return _nanargmax_in(wrist_elevation, np.ones(len(wrist_elevation), bool))


def detect_trophy(
    knee_flexion: np.ndarray, toss_arm_raise: np.ndarray, contact: int | None
) -> int | None:
    """Trophy: max knee flexion before contact while the tossing wrist is above its shoulder."""
    if contact is None:
        return None
    before = np.arange(len(knee_flexion)) < contact
    raised = np.nan_to_num(toss_arm_raise, nan=-np.inf) > 0
    return _nanargmax_in(knee_flexion, before & raised)


def detect_racket_drop(
    elbow_angle: np.ndarray, trophy: int | None, contact: int | None
) -> int | None:
    """Racket drop: the most flexed (smallest) hitting-elbow angle between trophy and contact."""
    if trophy is None or contact is None or contact - trophy < 2:
        return None
    frames = np.arange(len(elbow_angle))
    return _nanargmax_in(-elbow_angle, (frames > trophy) & (frames < contact))


def combined_knee_flexion(series: A.Series) -> np.ndarray:
    """Mean of both legs, falling back to whichever leg is visible."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(
            np.stack([series[A.FRONT_KNEE_FLEXION], series[A.BACK_KNEE_FLEXION]]), axis=0
        )


def detect_phases(series: A.Series) -> PhaseFrames:
    contact = detect_contact(series[A.WRIST_ELEVATION_PX])
    trophy = detect_trophy(combined_knee_flexion(series), series[A.TOSS_ARM_RAISE_PX], contact)
    racket_drop = detect_racket_drop(series[A.ELBOW_ANGLE], trophy, contact)
    return PhaseFrames(trophy=trophy, racket_drop=racket_drop, contact=contact)


PHASE_SEGMENTS = [
    ("trophy", "Trophy"),
    ("racket_drop", "Racket drop"),
    ("contact", "Contact / follow-through"),
]


def phase_label(frame: int, phases: PhaseFrames) -> str:
    """Name of the phase segment a frame falls in, for the video overlay."""
    label = "Stance"
    for attr, name in PHASE_SEGMENTS:
        start = getattr(phases, attr)
        if start is not None and frame >= start:
            label = name
    return label

"""Heuristic serve phase detection.

Each detector takes per-frame arrays and returns a frame index, or None if
the phase cannot be found. They are kept separate so any one can later be
replaced by a learned classifier with the same signature.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

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
    knee_flexion: np.ndarray,
    toss_arm_raise: np.ndarray,
    contact: int | None,
    window: int | None = None,
    plateau_deg: float | None = None,
) -> int | None:
    """Trophy: max knee flexion before contact while the tossing wrist is above its shoulder.

    ``window`` (frames) limits the search to just before contact, so an early
    knee bend (e.g. while bouncing the ball) can't be mistaken for the trophy.
    ``plateau_deg`` returns the centre of all frames within that many degrees
    of the peak instead of the single highest frame, which is steadier when
    foreshortening flattens the curve.
    """
    if contact is None:
        return None
    frames = np.arange(len(knee_flexion))
    before = frames < contact
    if window is not None:
        before &= frames >= contact - window
    raised = np.nan_to_num(toss_arm_raise, nan=-np.inf) > 0
    peak = _nanargmax_in(knee_flexion, before & raised)
    if peak is None or plateau_deg is None:
        return peak
    near = (before & raised) & (np.nan_to_num(knee_flexion, nan=-np.inf) >= knee_flexion[peak] - plateau_deg)
    return int(round(np.flatnonzero(near).mean()))


def detect_racket_drop(
    elbow_angle: np.ndarray, trophy: int | None, contact: int | None
) -> int | None:
    """Racket drop: the most flexed (smallest) hitting-elbow angle between trophy and contact."""
    if trophy is None or contact is None or contact - trophy < 2:
        return None
    frames = np.arange(len(elbow_angle))
    return _nanargmax_in(-elbow_angle, (frames > trophy) & (frames < contact))


def detect_trophy_toss_peak(
    toss_wrist_elevation: np.ndarray, contact: int | None, window: int | None = None
) -> int | None:
    """Trophy: the toss hand's highest point before contact.

    It's a vertical signal, so it survives any level camera angle, unlike
    knee flexion, which foreshortens from behind.
    """
    if contact is None:
        return None
    frames = np.arange(len(toss_wrist_elevation))
    mask = frames < contact
    if window is not None:
        mask &= frames >= contact - window
    return _nanargmax_in(toss_wrist_elevation, mask)


def detect_racket_drop_wrist_low(
    wrist_elevation: np.ndarray, trophy: int | None, contact: int | None
) -> int | None:
    """Racket drop: the hitting wrist's lowest point between trophy and contact (vertical signal)."""
    if trophy is None or contact is None or contact - trophy < 2:
        return None
    frames = np.arange(len(wrist_elevation))
    return _nanargmax_in(-wrist_elevation, (frames > trophy) & (frames < contact))


def is_complete_serve(series: A.Series, contact: int | None) -> bool:
    """A serve needs a toss before contact and the hitting wrist above the head at contact.

    Rejects clips that end mid-toss, where the highest wrist is just part of a
    ball bounce.
    """
    if contact is None:
        return False
    tossed = np.nan_to_num(series[A.TOSS_ARM_RAISE_PX][:contact], nan=-np.inf) > 0
    wrist = series[A.WRIST_ELEVATION_PX][contact]
    nose = series[A.NOSE_ELEVATION_PX][contact]
    return bool(tossed.any()) and not np.isnan(wrist) and not np.isnan(nose) and wrist > nose


@dataclass(frozen=True)
class ServeShape:
    """Thresholds for ``serve_rejection``, in torso lengths and seconds.

    Each is about 70% of the weakest value measured on 24 real serves (see
    docs/serve-check.md), so it sits clear of every serve rather than being tuned
    to the non-serve clips.
    """

    wrist_above_nose: float = 0.3   # serves: >= 0.43
    toss_below_hitting_wrist: float = 0.5  # serves: >= 1.09
    toss_lead_s: float = 0.2        # serves: >= 0.30
    toss_rise: float = 0.9          # serves: >= 1.26
    toss_search_s: float = 1.5      # the toss peak is looked for this long before contact


REJECTION_MESSAGES = {
    "no_contact": "We couldn't find a swing that reaches above the head.",
    "no_toss": "We couldn't find a ball toss before the swing.",
    "wrist_not_above_head": "The hitting arm doesn't reach above the head, as it does at serve contact.",
    "both_hands_up": "Both hands are up at the highest point of the swing; in a serve the tossing arm has come down by contact.",
    "toss_too_late": "The tossing hand peaks at the same moment as the swing, rather than before it.",
    "no_toss_rise": "The tossing hand doesn't rise enough to toss a ball.",
}


def serve_rejection(
    series: A.Series, contact: int | None, fps: float, shape: ServeShape = ServeShape()
) -> str | None:
    """Why this doesn't look like a serve (a ``REJECTION_MESSAGES`` key), or None if it does.

    A serve is a toss that rises and peaks first, then a swing that reaches well above the
    head while the tossing arm drops. Forehands, backhands, smashes, throws and exercises
    miss at least one of these on the evaluation clips. Checks whose joints are hidden pass,
    so an occluded toss arm can't reject a real serve.
    """
    if contact is None:
        return "no_contact"
    torso = np.nanmedian(series[A.TORSO_LENGTH_PX]) if np.any(~np.isnan(series[A.TORSO_LENGTH_PX])) else np.nan
    if not np.isfinite(torso) or torso <= 0:
        return None
    wrist = series[A.WRIST_ELEVATION_PX]
    toss = series[A.TOSS_WRIST_ELEVATION_PX]
    nose = series[A.NOSE_ELEVATION_PX][contact]
    if not np.isnan(nose) and (wrist[contact] - nose) / torso < shape.wrist_above_nose:
        return "wrist_not_above_head"
    if not np.isnan(toss[contact]) and (wrist[contact] - toss[contact]) / torso < shape.toss_below_hitting_wrist:
        return "both_hands_up"
    start = max(0, contact - round(shape.toss_search_s * fps))
    window = toss[start:contact]
    if window.size == 0 or np.isnan(window).all():
        return None
    peak = start + int(np.nanargmax(window))
    if (contact - peak) / fps < shape.toss_lead_s:
        return "toss_too_late"
    # The climb is measured from the start of the clip, not the window: in slow motion
    # the hand starts rising seconds of video before contact.
    if (toss[peak] - np.nanmin(toss[: peak + 1])) / torso < shape.toss_rise:
        return "no_toss_rise"
    return None


def combined_knee_flexion(series: A.Series) -> np.ndarray:
    """Mean of both legs, falling back to whichever leg is visible."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(
            np.stack([series[A.FRONT_KNEE_FLEXION], series[A.BACK_KNEE_FLEXION]]), axis=0
        )


TROPHY_METHODS = ("knee_toss", "toss_peak")
RACKET_DROP_METHODS = ("min_elbow", "wrist_low")


def detect_phases(
    series: A.Series,
    trophy_method: str = "knee_toss",
    racket_drop_method: str = "min_elbow",
    require_complete_serve: bool = False,
    trophy_window: int | None = None,
    trophy_fallback: bool = False,
    contact_series: A.Series | None = None,
    trophy_plateau_deg: float | None = None,
) -> PhaseFrames:
    """Detect all phases. ``contact_series`` (optional) supplies the wrist and
    nose heights used for contact, e.g. cleaned with a looser visibility
    threshold than the angles."""
    if trophy_method not in TROPHY_METHODS or racket_drop_method not in RACKET_DROP_METHODS:
        raise ValueError(f"Unknown phase method: {trophy_method!r} / {racket_drop_method!r}")
    cs = contact_series if contact_series is not None else series
    contact = detect_contact(cs[A.WRIST_ELEVATION_PX])
    if require_complete_serve:
        heights = {k: cs[k] for k in (A.WRIST_ELEVATION_PX, A.NOSE_ELEVATION_PX)}
        if not is_complete_serve({**series, **heights}, contact):
            return PhaseFrames()
    if trophy_method == "toss_peak":
        trophy = detect_trophy_toss_peak(series[A.TOSS_WRIST_ELEVATION_PX], contact, trophy_window)
    else:
        trophy = detect_trophy(
            combined_knee_flexion(series), series[A.TOSS_ARM_RAISE_PX], contact, trophy_window, trophy_plateau_deg
        )
        if trophy is None and trophy_fallback:
            trophy = detect_trophy_toss_peak(series[A.TOSS_WRIST_ELEVATION_PX], contact, trophy_window)
    if racket_drop_method == "wrist_low":
        racket_drop = detect_racket_drop_wrist_low(series[A.WRIST_ELEVATION_PX], trophy, contact)
    else:
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

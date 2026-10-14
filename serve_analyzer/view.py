"""Where the camera was: an estimate of the camera's angle around the player, from the landmarks.

Angles are measured around the player, relative to the court and the hitting hand, so they
mean the same for left- and right-handers:

    0 = behind the baseline · 90 = the hitting-arm sideline · 180 = across the net · 270 = the
    tossing-arm sideline

The cue is the line from the tossing shoulder to the hitting shoulder (and the same for the
hips). How long it looks across the picture, and which end MediaPipe puts nearer the camera,
give the camera's angle around the *body*. At the set position just before the toss, servers
stand side-on to the net, so subtracting that stance turn gives the angle around the *court*.
That's measured over the moment before the toss starts to rise: earlier, players often face
the net while bouncing the ball.

See docs/view-detection.md for how well it works and what it changes in the results.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import landmarks as L
from .models import Hand, PoseSequence

# How far servers are turned at the set position: the chest faces this far round from the net,
# toward the hitting-arm sideline. Tuned on the synthetic rig and the labelled clips
# (docs/view-detection.md).
STANCE_TURN_DEG = 80.0
SET_WINDOW_S = 0.25          # the stance is averaged over this long before the toss starts
TOSS_SEARCH_S = 1.5          # the toss peak is looked for this long before contact
TOSS_START_SEARCH_S = 1.2    # and the start of the toss this long before its peak
MIN_VISIBILITY = 0.3         # landmarks less visible than this don't count toward the estimate


def _hand_sign(hand: Hand) -> float:
    """Image x is mirrored for left-handers, so the hitting side is always +90."""
    return 1.0 if hand is Hand.RIGHT else -1.0


def set_position_window(seq: PoseSequence, hand: Hand, contact: int | None) -> tuple[int, int]:
    """Frames [start, end) of the set position: the moment before the toss starts to rise."""
    fps = seq.fps
    toss = -seq.landmarks[:, L.tossing_arm(hand).wrist, 1]  # higher in the picture = larger
    n = seq.n_frames
    end_search = contact if contact is not None else n
    start_search = max(0, end_search - round(TOSS_SEARCH_S * fps))
    window = toss[start_search:end_search]
    if window.size == 0 or np.isnan(window).all():
        start = max(0, (contact or n) - round(1.0 * fps))
        return start, min(n, start + max(1, round(SET_WINDOW_S * fps)))
    peak = start_search + int(np.nanargmax(window))
    lo = max(0, peak - round(TOSS_START_SEARCH_S * fps))
    before = toss[lo:peak + 1]
    toss_start = lo + int(np.nanargmin(before)) if not np.isnan(before).all() else lo
    first = max(0, toss_start - round(SET_WINDOW_S * fps))
    return first, max(first + 1, toss_start + 1)


@dataclass(frozen=True)
class BodyTurn:
    """The camera's angle around the body over some frames, and how much to trust it."""

    angle_deg: float | None   # 0 = the camera faces the player's back... see body_angle
    strength: float           # 0-1: how consistent the frames and the two cues were
    frames: int               # frames that had the landmarks


def body_angle(seq: PoseSequence, hand: Hand, frames: slice) -> BodyTurn:
    """The camera's angle around the player's body, from the shoulder and hip lines.

    For the line from the tossing shoulder to the hitting shoulder, ``across`` is its length
    across the picture (hand-mirrored) and ``depth`` how much farther from the camera the
    hitting end is. For a line at angle a around the body, (across, depth) = (cos a, -sin a)
    times its length, so a = atan2(-depth, across).
    """
    if seq.world is None or seq.world.shape[0] != seq.n_frames:
        return BodyTurn(None, 0.0, 0)
    hit, toss = L.hitting_arm(hand), L.tossing_arm(hand)
    hit_hip, toss_hip = L.back_leg(hand).hip, L.front_leg(hand).hip
    w = seq.world[frames]
    vis = seq.landmarks[frames, :, 2]
    sign = _hand_sign(hand)
    vectors = []
    for a, b in ((hit.shoulder, toss.shoulder), (hit_hip, toss_hip)):
        ok = (vis[:, a] >= MIN_VISIBILITY) & (vis[:, b] >= MIN_VISIBILITY)
        d = w[:, a] - w[:, b]
        across, depth = sign * d[:, 0], d[:, 2]
        good = ok & np.isfinite(across) & np.isfinite(depth)
        vectors.append(np.stack([across[good], -depth[good]], axis=1))
    v = np.concatenate(vectors) if vectors else np.empty((0, 2))
    if len(v) == 0:
        return BodyTurn(None, 0.0, 0)
    unit = v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)
    mean = unit.mean(axis=0)
    strength = float(np.linalg.norm(mean))  # 1 when every frame and both lines agree
    angle = float(np.degrees(np.arctan2(mean[1], mean[0])) % 360)
    return BodyTurn(angle, strength, len(v))


# Categories by the estimated angle around the court (hand-relative degrees). Each spans 45°
# around its centre; the synthetic rig's cameras sit inside them (behind-diagonal at 30°,
# front-diagonal at 135°).
CATEGORIES = (
    ("behind", 0.0), ("behind-diagonal", 45.0), ("side-on", 90.0), ("front-diagonal", 135.0),
    ("front", 180.0), ("front-diagonal", 225.0), ("side-on", 270.0), ("behind-diagonal", 315.0),
)
MIN_CONFIDENCE = 0.5


@dataclass(frozen=True)
class ViewEstimate:
    category: str            # one of CATEGORIES' names
    side: str | None         # "hitting" or "toss" for side-on and diagonal views, else None
    angle_deg: float         # around the court: 0 behind, 90 hitting side, 180 front, 270 toss side
    confidence: float        # 0-1; below MIN_CONFIDENCE the estimate isn't acted on
    frames: tuple[int, int]  # the frames it was measured over


def categorise(angle_deg: float) -> tuple[str, str | None, float]:
    """(category, side, how far inside the category 0-1: 1 at its centre, 0 at its edge)."""
    a = angle_deg % 360
    name, centre = min(CATEGORIES, key=lambda c: abs((a - c[1] + 180) % 360 - 180))
    offset = abs((a - centre + 180) % 360 - 180)
    side = None if name in ("behind", "front") else ("hitting" if 0 < a < 180 else "toss")
    return name, side, max(0.0, 1.0 - offset / 22.5)


def estimate_view(
    seq: PoseSequence, hand: Hand, contact: int | None, *,
    frames: tuple[int, int] | None = None, turn_deg: float = STANCE_TURN_DEG,
) -> ViewEstimate | None:
    """The camera's angle around the court, from the body's turn at the set position
    (or over ``frames``) minus the turn servers usually have then (``turn_deg``)."""
    start, end = frames if frames is not None else set_position_window(seq, hand, contact)
    turn = body_angle(seq, hand, slice(start, end))
    if turn.angle_deg is None:
        return None
    angle = (turn.angle_deg - turn_deg) % 360
    name, side, inside = categorise(angle)
    # Confidence: the frames agree (strength), and the angle isn't on a category's edge.
    confidence = turn.strength * (0.5 + 0.5 * inside)
    return ViewEstimate(name, side, angle, round(confidence, 3), (start, end))


# --- the camera position people choose at upload ------------------------------------------------
#
# Detecting the view automatically missed its targets (docs/view-detection.md), so the person is
# asked instead. Positions are relative to the hitting hand, like the angles above.

CAMERA_VIEWS = (
    "side_hitting", "side_toss", "behind", "behind_diagonal_hitting", "behind_diagonal_toss",
    "front", "front_diagonal_hitting", "front_diagonal_toss",
)
MEASURED, APPROXIMATE, UNREADABLE = "measured", "approximate", "unreadable"
MEASURED_WITHIN = {"angle": 10.0, "wrist_height": 0.1}  # degrees, body heights


def _reliability_table() -> dict[str, dict[str, float]]:
    import json
    from importlib import resources

    return json.loads(resources.files("serve_analyzer").joinpath("data/view_reliability.json").read_text())["views"]


def measurement_quality(camera_view: str | None, ranges: dict) -> dict[str, dict[str, str]] | None:
    """How far each measurement can be trusted from ``camera_view``: {phase: {metric: quality}}.

    From the rig's error for that view (data/view_reliability.json):
    - "measured": within 10° (0.1 body heights for wrist height);
    - "approximate": within the width of the measurement's good range, so it can still place
      you roughly in or out of it;
    - "unreadable": wider than that, so its good/borderline/off label would be noise.
    None when the camera position isn't known: then everything is shown as measured.
    ``ranges`` is the reference table as a dict ({phase: {metric: {"good": [lo, hi], ...}}}).
    """
    if camera_view is None:
        return None
    if camera_view not in CAMERA_VIEWS:
        raise ValueError(f"unknown camera view {camera_view!r}")
    errors = _reliability_table()[camera_view]
    out: dict[str, dict[str, str]] = {}
    for key, error in errors.items():
        phase, metric = key.split(".")
        rng = ranges.get(phase, {}).get(metric)
        if rng is None:
            continue
        bar = MEASURED_WITHIN["wrist_height" if metric == "wrist_height" else "angle"]
        width = rng["good"][1] - rng["good"][0]
        quality = MEASURED if error <= bar else APPROXIMATE if error <= width else UNREADABLE
        out.setdefault(phase, {})[metric] = quality
    return out


HIDDEN_ARM_VISIBILITY = 0.4


def hitting_arm_hidden(seq: PoseSequence, hand: Hand, trophy: int | None) -> bool:
    """Whether the hitting arm was mostly out of sight around the trophy position.

    Deliberately says nothing about which side the camera was on: MediaPipe's left/right swaps
    in profile make the arm look hidden on some clips filmed from the hitting side too.
    """
    if trophy is None:
        return False
    arm = L.hitting_arm(hand)
    window = seq.landmarks[max(0, trophy - 2):trophy + 3]
    vis = [np.nanmedian(window[:, j, 2]) for j in (arm.elbow, arm.wrist)]
    return bool(np.nanmean(vis) < HIDDEN_ARM_VISIBILITY)

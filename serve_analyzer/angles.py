"""Joint-angle maths and per-frame kinematic series."""

from __future__ import annotations

import warnings

import numpy as np

from . import landmarks as L
from .models import Hand, PoseSequence

FRONT_KNEE_FLEXION = "front_knee_flexion"
BACK_KNEE_FLEXION = "back_knee_flexion"
ELBOW_ANGLE = "elbow_angle"
TRUNK_TILT = "trunk_tilt"
WRIST_HEIGHT = "wrist_height"
WRIST_ELEVATION_PX = "wrist_elevation_px"
TOSS_ARM_RAISE_PX = "toss_arm_raise_px"
TOSS_WRIST_ELEVATION_PX = "toss_wrist_elevation_px"
NOSE_ELEVATION_PX = "nose_elevation_px"

ANGLE_SPACES = ("image2d", "world3d")

METRIC_NAMES = [FRONT_KNEE_FLEXION, BACK_KNEE_FLEXION, ELBOW_ANGLE, TRUNK_TILT, WRIST_HEIGHT]

Series = dict[str, np.ndarray]


def joint_angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Angle ABC at vertex b in degrees, in [0, 180].

    Inputs are (..., 2) or (..., 3) arrays. Returns NaN where any point is
    missing or a segment has zero length.
    """
    ba = np.asarray(a, float) - np.asarray(b, float)
    bc = np.asarray(c, float) - np.asarray(b, float)
    if ba.shape[-1] == 2:
        cross = np.abs(ba[..., 0] * bc[..., 1] - ba[..., 1] * bc[..., 0])
    else:
        cross = np.linalg.norm(np.cross(ba, bc), axis=-1)
    dot = (ba * bc).sum(axis=-1)
    angle = np.degrees(np.arctan2(cross, dot))
    degenerate = (np.linalg.norm(ba, axis=-1) == 0) | (np.linalg.norm(bc, axis=-1) == 0)
    return np.where(degenerate, np.nan, angle)


def tilt_from_vertical(bottom: np.ndarray, top: np.ndarray) -> np.ndarray:
    """Unsigned angle in degrees between the bottom->top segment and "up".

    Works for image points and camera-aligned world points: in both, y grows
    downwards, so up is -y. (That assumes a level camera.)
    """
    up = np.zeros_like(np.asarray(bottom, float))
    up[..., 1] = -1.0
    return joint_angle(np.asarray(bottom, float) + up, bottom, top)


def _nanmean(*arrays: np.ndarray) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(np.stack(arrays), axis=0)


def compute_series(seq: PoseSequence, hand: Hand, space: str = "image2d") -> Series:
    """Per-frame kinematic series used for phase detection and metrics.

    ``wrist_height`` is normalised by body height (lower ankle to nose), so
    1.0 means "at nose height" regardless of distance from the camera. The
    ``*_px`` series are raw image heights (up is positive); they need no
    ankles, so phase detection still works when the feet are occluded.

    ``space="world3d"`` measures the knee, elbow and trunk angles from the
    3D world landmarks instead, so they don't depend on the camera angle.
    Heights and the phase signals stay in image space: vertical survives
    any level camera, and they don't need the noisier depth estimate.
    """
    if space not in ANGLE_SPACES:
        raise ValueError(f"Unknown angle space {space!r}")
    p = seq.xy
    hit, toss = L.hitting_arm(hand), L.tossing_arm(hand)
    front, back = L.front_leg(hand), L.back_leg(hand)

    mid_shoulder = _nanmean(p(L.LEFT_SHOULDER), p(L.RIGHT_SHOULDER))
    mid_hip = _nanmean(p(L.LEFT_HIP), p(L.RIGHT_HIP))

    ankles = np.stack([p(L.LEFT_ANKLE), p(L.RIGHT_ANKLE)])  # (2, frames, 2)
    ankle_y = np.where(np.isnan(ankles[..., 1]), -np.inf, ankles[..., 1])
    lower = ankles[ankle_y.argmax(axis=0), np.arange(seq.n_frames)]  # lower ankle per frame
    ground_y = lower[:, 1]
    nose = p(L.NOSE)
    body_height = np.hypot(nose[:, 0] - lower[:, 0], nose[:, 1] - lower[:, 1])
    body_height = np.where(body_height > 0, body_height, np.nan)

    def height(index: int) -> np.ndarray:
        return (ground_y - p(index)[:, 1]) / body_height

    use_world = space == "world3d" and seq.world is not None

    def q(index: int) -> np.ndarray:
        return seq.world[:, index, :] if use_world else p(index)

    shoulder_mid = _nanmean(q(L.LEFT_SHOULDER), q(L.RIGHT_SHOULDER)) if use_world else mid_shoulder
    hip_mid = _nanmean(q(L.LEFT_HIP), q(L.RIGHT_HIP)) if use_world else mid_hip

    def knee_flexion(leg: L.LegSide) -> np.ndarray:
        return 180.0 - joint_angle(q(leg.hip), q(leg.knee), q(leg.ankle))

    return {
        FRONT_KNEE_FLEXION: knee_flexion(front),
        BACK_KNEE_FLEXION: knee_flexion(back),
        ELBOW_ANGLE: joint_angle(q(hit.shoulder), q(hit.elbow), q(hit.wrist)),
        TRUNK_TILT: tilt_from_vertical(hip_mid, shoulder_mid),
        WRIST_HEIGHT: height(hit.wrist),
        WRIST_ELEVATION_PX: -p(hit.wrist)[:, 1],
        TOSS_ARM_RAISE_PX: p(toss.shoulder)[:, 1] - p(toss.wrist)[:, 1],
        TOSS_WRIST_ELEVATION_PX: -p(toss.wrist)[:, 1],
        NOSE_ELEVATION_PX: -p(L.NOSE)[:, 1],
    }

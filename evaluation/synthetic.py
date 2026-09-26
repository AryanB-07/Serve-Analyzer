"""Synthetic multi-view serves with exact ground truth.

A scripted 3D serve (parameterised stance, knee depth, handedness) is filmed by
virtual pinhole cameras placed around the player, then passed through a detector
noise model so the pipeline sees something like MediaPipe output: 2D landmarks
with visibility and hip-centred, camera-aligned world landmarks.

World frame of the generator: +X = server's right sideline (for a right-hander),
+Y = up, +Z = toward the net.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from serve_analyzer.models import Hand, PhaseFrames, PoseSequence

NOSE, LS, RS, LE, RE, LW, RW, LH, RH, LK, RK, LA, RA = 0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28
MIRROR_PAIRS = [(LS, RS), (LE, RE), (LW, RW), (LH, RH), (LK, RK), (LA, RA)]
UP = np.array([0.0, 1.0, 0.0])


@dataclass(frozen=True)
class ServeSpec:
    """Knobs for one synthetic serve. Phase frames are given at 30 fps and scaled."""

    knee_dir_deg: float = 45.0   # where the knees point: 0 = net, 90 = the hitting-hand sideline
    knee_peak_deg: float = 62.0  # knee flexion at trophy
    hand: Hand = Hand.RIGHT
    fps: float = 30.0
    seed: int = 0

    @property
    def scale(self) -> float:
        return self.fps / 30.0


def rotation(axis: np.ndarray, deg: float) -> np.ndarray:
    """Rodrigues rotation matrix about ``axis`` by ``deg`` degrees."""
    axis = axis / np.linalg.norm(axis)
    a = np.radians(deg)
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + np.sin(a) * k + (1 - np.cos(a)) * k @ k


@dataclass
class SyntheticServe:
    spec: ServeSpec
    joints: np.ndarray  # (frames, 33, 3) metres in the generator world frame; NaN for unused landmarks
    phases: PhaseFrames
    fps: float
    extra: dict = field(default_factory=dict)


def make_serve(spec: ServeSpec) -> SyntheticServe:
    s = spec.scale
    n = int(round(60 * s))
    trophy, drop, contact = int(round(30 * s)), int(round(40 * s)), int(round(46 * s))

    def curve(keys):
        frames, values = zip(*keys)
        return np.interp(np.arange(n), [f * s for f in frames], values)

    kp = spec.knee_peak_deg
    knee = curve([(0, 8), (30, kp), (40, kp * 0.4), (46, 3), (59, 10)])
    elbow = curve([(0, 150), (30, 100), (40, 50), (46, 172), (59, 150)])
    abduct = curve([(0, 20), (30, 95), (40, 110), (46, 172), (59, 60)])
    toss = curve([(0, 10), (26, 170), (30, 165), (46, 40), (59, 20)])
    lean = curve([(0, 2), (30, 22), (40, 15), (46, 8), (59, 5)])
    yaw = curve([(0, 80), (30, 75), (40, 55), (46, 10), (59, 0)])  # chest direction: 90 = +X, 0 = +Z

    kd = np.radians(spec.knee_dir_deg)
    kfwd = np.array([np.sin(kd), 0.0, np.cos(kd)])
    kaxis = -np.cross(kfwd, UP)
    joints = np.full((n, 33, 3), np.nan)
    for i in range(n):
        fwd = np.array([np.sin(np.radians(yaw[i])), 0.0, np.cos(np.radians(yaw[i]))])
        right = -np.cross(fwd, UP)
        right /= np.linalg.norm(right)
        P = joints[i]
        pelvis = np.array([0.0, 1.0, 0.0])
        P[LH], P[RH] = pelvis - 0.12 * right, pelvis + 0.12 * right
        for hip, kn, an in ((LH, LK, LA), (RH, RK, RA)):
            P[kn] = P[hip] + 0.45 * (rotation(kaxis, -knee[i] / 2) @ -UP)
            P[an] = P[kn] + 0.45 * (rotation(kaxis, knee[i] / 2) @ -UP)
        T = rotation(fwd, lean[i])
        spine = T @ UP
        mid_sh = pelvis + 0.5 * spine
        P[LS], P[RS] = mid_sh - 0.19 * (T @ right), mid_sh + 0.19 * (T @ right)
        P[NOSE] = pelvis + 0.72 * spine + 0.09 * fwd
        upper = rotation(fwd, abduct[i]) @ (T @ -UP)
        P[RE] = P[RS] + 0.3 * upper
        bend = np.cross(upper, -fwd)
        bend /= np.linalg.norm(bend)
        P[RW] = P[RE] + 0.28 * (rotation(bend, 180 - elbow[i]) @ upper)
        tup = rotation(fwd, -toss[i]) @ (T @ -UP)
        P[LE] = P[LS] + 0.3 * tup
        P[LW] = P[LE] + 0.28 * (rotation(fwd, -8) @ tup)

    if spec.hand is Hand.LEFT:  # mirror across the X = 0 plane and relabel sides
        joints[..., 0] *= -1
        for a, b in MIRROR_PAIRS:
            joints[:, [a, b]] = joints[:, [b, a]]
    return SyntheticServe(spec, joints, PhaseFrames(trophy, drop, contact), spec.fps)


# --- ground truth using the pipeline's metric definitions, in exact 3D ---------------------

def _angle(a, b, c):
    u, v = a - b, c - b
    return np.degrees(np.arctan2(np.linalg.norm(np.cross(u, v), axis=-1), (u * v).sum(-1)))


def true_series(serve: SyntheticServe) -> dict[str, np.ndarray]:
    X, hand = serve.joints, serve.spec.hand
    hs, he, hw = (RS, RE, RW) if hand is Hand.RIGHT else (LS, LE, LW)
    front = (LH, LK, LA) if hand is Hand.RIGHT else (RH, RK, RA)
    back = (RH, RK, RA) if hand is Hand.RIGHT else (LH, LK, LA)
    lower = np.where((X[:, LA, 1] <= X[:, RA, 1])[:, None], X[:, LA], X[:, RA])
    mid_sh, mid_hip = (X[:, LS] + X[:, RS]) / 2, (X[:, LH] + X[:, RH]) / 2
    spine = mid_sh - mid_hip
    return {
        "front_knee_flexion": 180 - _angle(X[:, front[0]], X[:, front[1]], X[:, front[2]]),
        "back_knee_flexion": 180 - _angle(X[:, back[0]], X[:, back[1]], X[:, back[2]]),
        "elbow_angle": _angle(X[:, hs], X[:, he], X[:, hw]),
        "trunk_tilt": np.degrees(np.arccos(np.clip(spine[:, 1] / np.linalg.norm(spine, axis=-1), -1, 1))),
        "wrist_height": (X[:, hw, 1] - lower[:, 1]) / np.linalg.norm(X[:, NOSE] - lower, axis=-1),
    }


# --- cameras and the detector noise model ------------------------------------------------

@dataclass(frozen=True)
class Camera:
    """``azimuth``: 0 = behind the baseline, 90 = hitting-hand sideline (for a right-hander),
    180 = across the net, 270 = the other sideline. ``height``: metres above hip height."""

    name: str
    group: str
    azimuth: float
    height: float = 0.0
    distance: float = 8.0
    focal_px: float = 2200.0
    width: int = 1920
    height_px: int = 1080


CAMERAS = [
    Camera("behind", "behind", 0),
    Camera("behind-diagonal (hitting side)", "behind-diagonal", 30),
    Camera("behind-diagonal (toss side)", "behind-diagonal", 330),
    Camera("side-on (hitting side)", "side-on", 90),
    Camera("side-on (toss side)", "side-on", 270),
    Camera("front-diagonal (hitting side)", "front-diagonal", 135),
    Camera("front-diagonal (toss side)", "front-diagonal", 225),
    Camera("front", "front", 180),
    Camera("side-on, 2 m high", "high", 90, height=2.0),
    Camera("behind, 2 m high", "high", 0, height=2.0),
]


@dataclass(frozen=True)
class NoiseModel:
    """Rough MediaPipe behaviour, calibrated against the real-clip probe (see docs).

    Joints more than ``occlusion_depth`` behind the torso get low visibility and
    larger errors, as MediaPipe does for the far side of the body. World
    landmarks get iid noise (larger in depth) and a per-clip depth compression,
    a known bias of monocular depth.
    """

    jitter_2d: float = 0.006        # x body height, visible joints
    jitter_2d_occluded: float = 0.02
    jitter_world: float = 0.012     # metres, visible joints
    jitter_world_occluded: float = 0.035
    depth_noise_factor: float = 1.5
    depth_scale_range: tuple[float, float] = (0.75, 1.0)
    occlusion_depth: float = 0.08   # metres behind the torso centre
    torso_margin: float = 1.25      # torso outline scale for "overlapping the body"
    visible: float = 0.95
    far_side: float = 0.7           # behind the torso but beside it: partly visible
    occluded: float = 0.2           # behind the torso and overlapping it in the image


NO_NOISE = NoiseModel(0, 0, 0, 0, 1.0, (1.0, 1.0), 99.0, 1.25, 0.99, 0.99, 0.99)


def _inside_torso(uv: np.ndarray, margin: float) -> np.ndarray:
    """Whether each 2D point lies inside the (scaled) shoulder-hip quadrilateral of its frame."""
    quad = uv[:, [LS, RS, RH, LH]]  # (frames, 4, 2) in order around the torso
    centre = np.nanmean(quad, axis=1, keepdims=True)
    quad = centre + margin * (quad - centre)
    inside = np.ones(uv.shape[:2], bool)
    sign = None
    for k in range(4):
        a, b = quad[:, k][:, None, :], quad[:, (k + 1) % 4][:, None, :]
        cross = (b[..., 0] - a[..., 0]) * (uv[..., 1] - a[..., 1]) - (b[..., 1] - a[..., 1]) * (uv[..., 0] - a[..., 0])
        s = np.sign(cross)
        sign = s if sign is None else sign
        inside &= (s == sign) | (s == 0)
    return inside


def film(serve: SyntheticServe, cam: Camera, noise: NoiseModel = NoiseModel()) -> PoseSequence:
    """Project ``serve`` through ``cam`` and apply ``noise``, returning what the pipeline sees."""
    rng = np.random.default_rng([serve.spec.seed, int(cam.azimuth), int(cam.height * 10)])
    X = serve.joints
    pivot = np.array([0.0, 1.0, 0.0])
    a = np.radians(cam.azimuth)
    center = pivot + cam.distance * np.array([np.sin(a), 0.0, -np.cos(a)]) + np.array([0, cam.height, 0])
    z = pivot - center
    z /= np.linalg.norm(z)
    x = np.cross(UP, z)
    x /= np.linalg.norm(x)
    y = -np.cross(z, x)  # image y points down
    R = np.stack([x, y, z])
    cam_pts = (X - center) @ R.T  # (frames, 33, 3) camera frame: x right, y down, z forward

    valid = ~np.isnan(X[..., 0])
    u = cam.focal_px * cam_pts[..., 0] / cam_pts[..., 2] + cam.width / 2
    v = cam.focal_px * cam_pts[..., 1] / cam_pts[..., 2] + cam.height_px / 2

    torso_depth = np.nanmean(cam_pts[:, [LS, RS, LH, RH], 2], axis=1)
    behind = cam_pts[..., 2] - torso_depth[:, None] > noise.occlusion_depth
    over_torso = _inside_torso(np.stack([u, v], axis=-1), noise.torso_margin)
    over_torso[:, [LS, RS, LH, RH]] = False  # the torso's own corners can't be hidden by it
    hidden = behind & over_torso
    far = behind & ~over_torso
    vis = np.select([hidden, far], [noise.occluded, noise.far_side], noise.visible)
    vis = np.where(valid, vis, 0.0)

    body_px = cam.focal_px * 1.7 / cam.distance
    mid = (noise.jitter_2d + noise.jitter_2d_occluded) / 2
    sigma = np.select([hidden, far], [noise.jitter_2d_occluded, mid], noise.jitter_2d) * body_px
    u = u + rng.normal(0, 1, u.shape) * sigma
    v = v + rng.normal(0, 1, v.shape) * sigma
    landmarks = np.stack([u, v, vis], axis=-1)

    hips = (cam_pts[:, LH] + cam_pts[:, RH]) / 2
    world = cam_pts - hips[:, None, :]
    depth_scale = rng.uniform(*noise.depth_scale_range)
    world[..., 2] *= depth_scale
    wmid = (noise.jitter_world + noise.jitter_world_occluded) / 2
    ws = np.select([hidden, far], [noise.jitter_world_occluded, wmid], noise.jitter_world)[..., None]
    world = world + rng.normal(0, 1, world.shape) * ws * np.array([1.0, 1.0, noise.depth_noise_factor])
    return PoseSequence(landmarks, serve.fps, cam.width, cam.height_px, world=world)


SERVE_SPECS = [
    ServeSpec(knee_dir, peak, hand, 30.0, seed)
    for seed, (knee_dir, peak, hand) in enumerate(
        (kd, pk, h) for kd in (30.0, 45.0, 60.0) for pk in (45.0, 65.0) for h in (Hand.RIGHT, Hand.LEFT)
    )
]

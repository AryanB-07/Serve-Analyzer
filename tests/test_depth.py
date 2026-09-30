import numpy as np
import pytest

from evaluation.depth import bone_depth_scale


def _swinging_bone(depth_scale: float, n: int = 60, sweep: float = np.pi / 2) -> tuple[np.ndarray, np.ndarray]:
    """A 0.4 m bone from joint 0 to joint 1 swinging from across the image to pointing at the
    camera, with its depth reported at ``depth_scale`` x the truth."""
    world = np.zeros((n, 2, 3))
    t = np.linspace(0, sweep, n)
    world[:, 1, 0] = 0.4 * np.cos(t)
    world[:, 1, 2] = 0.4 * np.sin(t) * depth_scale
    return world, np.ones((n, 2))


@pytest.mark.parametrize("s", [0.5, 0.8, 1.0, 1.4])
def test_bone_depth_scale_recovers_a_known_scale(s):
    world, vis = _swinging_bone(s)
    est, frames, _ = bone_depth_scale(world, vis, 0, 1)
    assert frames == 60
    assert est == pytest.approx(s, abs=0.02)


def test_bone_depth_scale_is_undefined_when_the_bone_never_turns_towards_the_camera():
    world, vis = _swinging_bone(1.0, sweep=0.05)
    assert np.isnan(bone_depth_scale(world, vis, 0, 1)[0])


def test_bone_depth_scale_ignores_low_visibility_frames():
    world, vis = _swinging_bone(0.7)
    vis[:45] = 0.1
    est, frames, _ = bone_depth_scale(world, vis, 0, 1)
    assert frames == 15 and np.isnan(est)


def test_rebuild_limb_depth_restores_a_compressed_elbow_angle():
    from serve_analyzer.angles import joint_angle, rebuild_limb_depth

    n = 40
    world = np.zeros((n, 33, 3))
    world[:, 12] = (0.0, 0.0, 0.0)  # right shoulder
    t = np.linspace(0, np.pi / 2, n)
    # Upper arm swings from across the image to pointing away from the camera; forearm points right.
    world[:, 14] = np.stack([-0.3 * np.cos(t), np.zeros(n), 0.3 * np.sin(t)], axis=1)
    world[:, 16] = world[:, 14] + (0.25, 0.0, 0.0)
    truth = joint_angle(world[:, 12], world[:, 14], world[:, 16])
    squashed = world.copy()
    squashed[..., 2] *= 0.3
    rebuilt = rebuild_limb_depth(squashed, percentile=100)
    before = np.abs(joint_angle(squashed[:, 12], squashed[:, 14], squashed[:, 16]) - truth)
    after = np.abs(joint_angle(rebuilt[:, 12], rebuilt[:, 14], rebuilt[:, 16]) - truth)
    assert after.max() < 0.5 and before.max() > 5


def test_swing_speed_halves_in_half_speed_slow_motion():
    from serve_analyzer.config import AnalysisConfig
    from serve_analyzer.models import PoseSequence
    from serve_analyzer.pipeline import measure, swing_speed

    from evaluation import synthetic as sy

    spec = sy.SERVE_SPECS[0]
    seq = sy.film(sy.make_serve(spec), sy.CAMERAS[0], sy.NO_NOISE)
    n = seq.n_frames
    fine = np.linspace(0, n - 1, 2 * n - 1)  # every frame twice as far apart in time
    slow = np.stack([np.interp(fine, np.arange(n), seq.landmarks[:, j, k]) for j in range(33) for k in range(3)], -1)
    slow_seq = PoseSequence(slow.reshape(-1, 33, 3), seq.fps, seq.width, seq.height)

    def speed(s: PoseSequence) -> float:
        pose, _, phases = measure(s, spec.hand, AnalysisConfig())
        return swing_speed(pose, spec.hand, phases.contact)

    assert speed(slow_seq) == pytest.approx(speed(seq) / 2, rel=0.15)

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

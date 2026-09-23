import numpy as np
import pytest

from serve_analyzer import angles as A
from serve_analyzer import landmarks as L
from serve_analyzer.models import Hand, PoseSequence

nan = np.nan


@pytest.mark.parametrize(
    "a,b,c,expected",
    [
        ((1, 0), (0, 0), (0, 1), 90.0),
        ((1, 0), (0, 0), (1, 1), 45.0),
        ((1, 0), (0, 0), (-1, 0), 180.0),
        ((1, 0), (0, 0), (2, 0), 0.0),
        ((0, -10), (0, 0), (10, 10), 135.0),
    ],
)
def test_joint_angle_known_values(a, b, c, expected):
    assert A.joint_angle(np.array(a), np.array(b), np.array(c)) == pytest.approx(expected)


def test_joint_angle_is_symmetric_and_scale_invariant():
    a, b, c = np.array([3.0, 7.0]), np.array([1.0, 2.0]), np.array([-4.0, 5.0])
    assert A.joint_angle(a, b, c) == pytest.approx(A.joint_angle(c, b, a))
    assert A.joint_angle(a * 5, b * 5, c * 5) == pytest.approx(A.joint_angle(a, b, c))


def test_joint_angle_precise_near_straight():
    eps = 1e-6
    angle = A.joint_angle(np.array([-1.0, 0.0]), np.array([0.0, 0.0]), np.array([1.0, eps]))
    assert 180 - angle == pytest.approx(np.degrees(eps), rel=1e-3)


def test_joint_angle_vectorised_with_nan_and_degenerate():
    a = np.array([[1.0, 0.0], [nan, 0.0], [0.0, 0.0]])
    b = np.zeros((3, 2))
    c = np.array([[0.0, 1.0], [0.0, 1.0], [0.0, 1.0]])
    out = A.joint_angle(a, b, c)
    assert out[0] == pytest.approx(90.0)
    assert np.isnan(out[1]) and np.isnan(out[2])


def test_tilt_from_vertical_uses_image_coordinates():
    hip = np.array([100.0, 200.0])
    assert A.tilt_from_vertical(hip, np.array([100.0, 100.0])) == pytest.approx(0.0)
    assert A.tilt_from_vertical(hip, np.array([200.0, 100.0])) == pytest.approx(45.0)
    assert A.tilt_from_vertical(hip, np.array([0.0, 100.0])) == pytest.approx(45.0)


def _standing_pose() -> np.ndarray:
    """One frame of a stick figure in pixel coordinates (y down), 33 landmarks."""
    lm = np.full((33, 3), nan)
    pts = {
        L.NOSE: (100, 0),
        L.LEFT_SHOULDER: (100, 30), L.RIGHT_SHOULDER: (100, 30),
        L.LEFT_ELBOW: (100, 60), L.RIGHT_ELBOW: (130, 30),   # right arm bent 90° at elbow
        L.LEFT_WRIST: (100, 90), L.RIGHT_WRIST: (130, 0),
        L.LEFT_HIP: (100, 100), L.RIGHT_HIP: (100, 100),
        L.LEFT_KNEE: (100, 150), L.RIGHT_KNEE: (120, 150),   # right knee bent
        L.LEFT_ANKLE: (100, 200), L.RIGHT_ANKLE: (100, 200),
    }
    for j, (x, y) in pts.items():
        lm[j] = (x, y, 1.0)
    return lm


def test_compute_series_on_stick_figure():
    seq = PoseSequence(_standing_pose()[None], fps=30.0, width=640, height=480)
    s = A.compute_series(seq, Hand.RIGHT)
    assert s[A.ELBOW_ANGLE][0] == pytest.approx(90.0)
    assert s[A.FRONT_KNEE_FLEXION][0] == pytest.approx(0.0)  # left leg straight
    assert s[A.BACK_KNEE_FLEXION][0] > 30.0
    assert s[A.TRUNK_TILT][0] == pytest.approx(0.0)
    assert s[A.WRIST_HEIGHT][0] == pytest.approx(1.0)  # wrist level with nose
    assert s[A.WRIST_ELEVATION_PX][0] == pytest.approx(0.0)
    assert s[A.TOSS_WRIST_ELEVATION_PX][0] == pytest.approx(-90.0)
    assert s[A.TOSS_ARM_RAISE_PX][0] == pytest.approx(-60.0)  # toss arm hanging down


def test_compute_series_handedness_swaps_sides():
    seq = PoseSequence(_standing_pose()[None], fps=30.0, width=640, height=480)
    s = A.compute_series(seq, Hand.LEFT)
    assert s[A.ELBOW_ANGLE][0] == pytest.approx(180.0)
    assert s[A.FRONT_KNEE_FLEXION][0] > 30.0
    assert s[A.BACK_KNEE_FLEXION][0] == pytest.approx(0.0)


def test_compute_series_falls_back_to_visible_side():
    lm = _standing_pose()
    lm[[L.LEFT_ANKLE, L.RIGHT_SHOULDER, L.RIGHT_HIP], :2] = nan
    s = A.compute_series(PoseSequence(lm[None], 30.0, 640, 480), Hand.RIGHT)
    assert s[A.TRUNK_TILT][0] == pytest.approx(0.0)
    assert s[A.WRIST_HEIGHT][0] == pytest.approx(1.0)

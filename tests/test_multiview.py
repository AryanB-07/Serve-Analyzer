"""Multi-view geometry, handedness and the tuned phase rules, on synthetic poses with known answers."""

import numpy as np
import pytest

from evaluation import synthetic as sy
from serve_analyzer import angles as A
from serve_analyzer.config import AnalysisConfig
from serve_analyzer.models import Hand, PhaseFrames, PoseSequence
from serve_analyzer.phases import (
    detect_phases,
    detect_racket_drop_wrist_low,
    detect_trophy,
    detect_trophy_toss_peak,
    is_complete_serve,
)
from serve_analyzer.pipeline import measure
from serve_analyzer.preprocessing import clean

nan = np.nan


# --- geometry -----------------------------------------------------------------------------

def test_joint_angle_in_3d_matches_known_values():
    assert A.joint_angle(np.array([1.0, 0, 0]), np.zeros(3), np.array([0, 0, 1.0])) == pytest.approx(90)
    assert A.joint_angle(np.array([1.0, 0, 0]), np.zeros(3), np.array([-1.0, 0, 0])) == pytest.approx(180)
    assert np.isnan(A.joint_angle(np.zeros(3), np.zeros(3), np.ones(3)))


def test_rotation_preserves_angles():
    a, b, c = np.array([0.3, 0.9, 0.1]), np.array([0.0, 0.5, 0.0]), np.array([0.2, 0.1, -0.4])
    R = sy.rotation(np.array([0.3, 1.0, -0.2]), 73)
    assert A.joint_angle(R @ a, R @ b, R @ c) == pytest.approx(A.joint_angle(a, b, c))


@pytest.mark.parametrize("cam", sy.CAMERAS, ids=lambda c: c.name)
def test_known_knee_angle_measures_the_same_from_any_camera_in_3d(cam):
    serve = sy.make_serve(sy.ServeSpec(knee_dir_deg=45, knee_peak_deg=90))
    truth = sy.true_series(serve)["front_knee_flexion"][serve.phases.trophy]
    assert truth == pytest.approx(90, abs=0.01)
    series = A.compute_series(sy.film(serve, cam, sy.NO_NOISE), Hand.RIGHT, "world3d")
    assert series[A.FRONT_KNEE_FLEXION][serve.phases.trophy] == pytest.approx(90, abs=0.5)


def test_2d_knee_angle_depends_on_the_camera():
    serve = sy.make_serve(sy.ServeSpec(knee_dir_deg=45, knee_peak_deg=90))
    readings = [
        A.compute_series(sy.film(serve, cam, sy.NO_NOISE), Hand.RIGHT, "image2d")[A.FRONT_KNEE_FLEXION][serve.phases.trophy]
        for cam in sy.CAMERAS
    ]
    assert np.ptp(readings) > 40  # the problem the 3D option exists to solve


def test_reprojection_matches_a_pinhole_camera():
    joints = np.full((1, 33, 3), np.nan)
    joints[0, sy.LH], joints[0, sy.RH] = [0, 1.0, -0.12], [0, 1.0, 0.12]  # hips straddle the pivot
    joints[0, sy.LS], joints[0, sy.RS] = [0, 1.5, -0.19], [0, 1.5, 0.19]
    joints[0, sy.NOSE] = [0, 2.0, 0]  # exactly 1 m above the pivot
    serve = sy.SyntheticServe(sy.ServeSpec(), joints, PhaseFrames(), 30.0)
    cam = sy.Camera("test", "test", 90, distance=10.0, focal_px=1000.0)
    seq = sy.film(serve, cam, sy.NO_NOISE)
    centre = np.array([cam.width / 2, cam.height_px / 2])
    hips = (seq.landmarks[0, sy.LH, :2] + seq.landmarks[0, sy.RH, :2]) / 2
    np.testing.assert_allclose(hips, centre, atol=1e-6)
    # f * 1 m / 10 m = 100 px above the centre (image y points down)
    np.testing.assert_allclose(seq.landmarks[0, sy.NOSE, :2], centre + [0, -100], atol=1e-6)


def test_world_landmarks_are_hip_centred_and_camera_aligned():
    serve = sy.make_serve(sy.ServeSpec())
    seq = sy.film(serve, sy.CAMERAS[0], sy.NO_NOISE)
    hips = (seq.world[:, sy.LH] + seq.world[:, sy.RH]) / 2
    np.testing.assert_allclose(hips, 0, atol=1e-9)
    assert np.all(seq.world[:, sy.NOSE, 1] < 0)  # y down: the head is above the hips


# --- handedness x view --------------------------------------------------------------------

@pytest.mark.parametrize("cam", [c for c in sy.CAMERAS if c.group in ("side-on", "behind")], ids=lambda c: c.name)
def test_left_hander_mirrors_a_right_hander(cam):
    right = sy.make_serve(sy.ServeSpec(hand=Hand.RIGHT))
    left = sy.make_serve(sy.ServeSpec(hand=Hand.LEFT))
    for serve, hand in ((right, Hand.RIGHT), (left, Hand.LEFT)):
        s = A.compute_series(sy.film(serve, cam, sy.NO_NOISE), hand, "world3d")
        assert s[A.ELBOW_ANGLE][serve.phases.contact] == pytest.approx(172, abs=0.5)
        assert s[A.FRONT_KNEE_FLEXION][serve.phases.trophy] == pytest.approx(62, abs=0.5)


def test_wrong_hand_measures_the_wrong_arm():
    left = sy.make_serve(sy.ServeSpec(hand=Hand.LEFT))
    seq = sy.film(left, sy.CAMERAS[0], sy.NO_NOISE)
    drop = left.phases.racket_drop
    assert A.compute_series(seq, Hand.LEFT, "world3d")[A.ELBOW_ANGLE][drop] == pytest.approx(50, abs=0.5)
    # With the wrong hand, the "hitting elbow" is the straight toss arm.
    assert A.compute_series(seq, Hand.RIGHT, "world3d")[A.ELBOW_ANGLE][drop] > 150


def test_a_mirrored_view_of_a_left_hander_equals_the_right_hander():
    # A left-hander filmed from the toss-side sideline looks like a right-hander filmed
    # from the other sideline, mirrored: 2D angles must agree.
    right = sy.make_serve(sy.ServeSpec(hand=Hand.RIGHT))
    left = sy.make_serve(sy.ServeSpec(hand=Hand.LEFT))
    r = A.compute_series(sy.film(right, sy.Camera("s", "s", 90), sy.NO_NOISE), Hand.RIGHT)
    l_ = A.compute_series(sy.film(left, sy.Camera("s", "s", 270), sy.NO_NOISE), Hand.LEFT)
    for key in (A.FRONT_KNEE_FLEXION, A.ELBOW_ANGLE, A.TRUNK_TILT):
        np.testing.assert_allclose(r[key], l_[key], atol=1e-6)


# --- cleaning of world landmarks ----------------------------------------------------------

def test_clean_masks_and_fills_world_landmarks_with_the_2d_visibility():
    lm = np.zeros((10, 33, 3))
    lm[..., 2] = 0.9
    lm[4:6, 16, 2] = 0.1
    world = np.tile(np.linspace(0, 1, 10)[:, None, None], (1, 33, 3))
    out = clean(PoseSequence(lm, 30.0, 640, 480, world=world), 0.5, 5, None)
    np.testing.assert_allclose(out.world[:, 16, 0], np.linspace(0, 1, 10))  # gap re-filled
    out_nofill = clean(PoseSequence(lm, 30.0, 640, 480, world=world), 0.5, 0, None)
    assert np.isnan(out_nofill.world[4:6, 16]).all()


# --- tuned phase rules --------------------------------------------------------------------

def test_trophy_window_ignores_an_early_knee_bend():
    knee = np.array([80.0] + [10.0] * 18 + [50.0] + [5.0] * 10)
    raised = np.ones_like(knee)
    assert detect_trophy(knee, raised, contact=29) == 0
    assert detect_trophy(knee, raised, contact=29, window=15) == 19


def test_toss_peak_and_wrist_low_rules():
    toss = np.array([0, 1, 5, 9, 7, 3, 0, 0.0])
    assert detect_trophy_toss_peak(toss, contact=7) == 3
    assert detect_trophy_toss_peak(toss, contact=7, window=2) == 5
    wrist = np.array([5, 3, 1, 4, 9.0])
    assert detect_racket_drop_wrist_low(wrist, trophy=0, contact=4) == 2


def _serve_series(n=30, contact=25, toss_up=range(10, 20), wrist_over_nose=True):
    s = {k: np.zeros(n) for k in (A.FRONT_KNEE_FLEXION, A.BACK_KNEE_FLEXION, A.ELBOW_ANGLE)}
    s[A.WRIST_ELEVATION_PX] = -np.abs(np.arange(n) - contact).astype(float)
    s[A.NOSE_ELEVATION_PX] = np.full(n, -5.0 if wrist_over_nose else 5.0)
    s[A.TOSS_ARM_RAISE_PX] = np.full(n, -10.0)
    s[A.TOSS_ARM_RAISE_PX][list(toss_up)] = 10.0
    s[A.TOSS_WRIST_ELEVATION_PX] = np.zeros(n)
    s[A.FRONT_KNEE_FLEXION][15] = 50
    return s


def test_complete_serve_check_rejects_a_clip_that_ends_mid_toss():
    assert is_complete_serve(_serve_series(), 25)
    assert not is_complete_serve(_serve_series(toss_up=[]), 25)
    assert not is_complete_serve(_serve_series(wrist_over_nose=False), 25)
    assert detect_phases(_serve_series(toss_up=[]), require_complete_serve=True) == PhaseFrames()
    assert detect_phases(_serve_series(), require_complete_serve=True).contact == 25


def test_trophy_fallback_uses_the_toss_peak_when_knees_are_missing():
    s = _serve_series()
    s[A.FRONT_KNEE_FLEXION][:] = nan
    s[A.BACK_KNEE_FLEXION][:] = nan
    s[A.TOSS_WRIST_ELEVATION_PX][18] = 30
    assert detect_phases(s).trophy is None
    assert detect_phases(s, trophy_fallback=True).trophy == 18


def test_unknown_methods_are_rejected():
    with pytest.raises(ValueError):
        detect_phases(_serve_series(), trophy_method="guess")
    with pytest.raises(ValueError):
        A.compute_series(sy.film(sy.make_serve(sy.ServeSpec()), sy.CAMERAS[0], sy.NO_NOISE), Hand.RIGHT, "5d")


# --- the tuned defaults, end to end on synthetic data ------------------------------------------

def test_default_config_times_phases_from_every_camera():
    serve = sy.make_serve(sy.ServeSpec(seed=7))
    errors = {"trophy": [], "racket_drop": [], "contact": []}
    for cam in sy.CAMERAS:
        _, _, phases = measure(sy.film(serve, cam), Hand.RIGHT, AnalysisConfig())
        for name in errors:
            detected = getattr(phases, name)
            assert detected is not None, (cam.name, name)
            errors[name].append(abs(detected - getattr(serve.phases, name)))
    assert max(errors["contact"]) <= 1
    assert np.mean(errors["trophy"]) <= 2 and np.mean(errors["racket_drop"]) <= 2

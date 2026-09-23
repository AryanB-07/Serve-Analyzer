import numpy as np

from serve_analyzer import angles as A
from serve_analyzer.models import PhaseFrames
from serve_analyzer.phases import (
    detect_contact,
    detect_phases,
    detect_racket_drop,
    detect_trophy,
    phase_label,
)

nan = np.nan
N = 60


def synthetic_serve() -> A.Series:
    """Idealised serve: trophy at 20, racket drop at 35, contact at 45."""
    t = np.arange(N, dtype=float)
    knee = 40 * np.exp(-((t - 20) ** 2) / 30)  # knees bend most at 20
    knee[5] = 80  # deeper bend earlier, but the toss arm is still down
    toss_raise = np.where((t >= 12) & (t <= 30), 50.0, -40.0)
    elbow = 170 - 100 * np.exp(-((t - 35) ** 2) / 10)
    elbow[55] = 30  # after contact: must be ignored
    wrist = -((t - 45) ** 2)  # wrist elevation peaks at 45
    return {
        A.FRONT_KNEE_FLEXION: knee,
        A.BACK_KNEE_FLEXION: knee.copy(),
        A.ELBOW_ANGLE: elbow,
        A.WRIST_ELEVATION_PX: wrist,
        A.TOSS_ARM_RAISE_PX: toss_raise,
    }


def test_detects_all_phases_on_synthetic_serve():
    assert detect_phases(synthetic_serve()) == PhaseFrames(trophy=20, racket_drop=35, contact=45)


def test_contact_ignores_nan_frames():
    wrist = np.array([1.0, 5.0, nan, 3.0])
    assert detect_contact(wrist) == 1


def test_contact_none_when_wrist_never_seen():
    assert detect_contact(np.full(10, nan)) is None


def test_trophy_requires_toss_arm_raised():
    knee = np.array([90.0, 10.0, 30.0, 20.0, 0.0])
    toss = np.array([-1.0, 5.0, 5.0, 5.0, 5.0])
    assert detect_trophy(knee, toss, contact=4) == 2


def test_trophy_only_considers_frames_before_contact():
    knee = np.array([10.0, 20.0, 99.0])
    toss = np.ones(3)
    assert detect_trophy(knee, toss, contact=2) == 1


def test_trophy_none_when_toss_arm_never_raised_or_no_contact():
    knee = np.array([10.0, 20.0, 30.0])
    assert detect_trophy(knee, np.full(3, -5.0), contact=2) is None
    assert detect_trophy(knee, np.full(3, nan), contact=2) is None
    assert detect_trophy(knee, np.ones(3), contact=None) is None


def test_trophy_uses_single_visible_leg():
    s = synthetic_serve()
    s[A.FRONT_KNEE_FLEXION][:] = nan
    assert detect_phases(s).trophy == 20


def test_racket_drop_is_strictly_between_trophy_and_contact():
    elbow = np.array([10.0, 120.0, 80.0, 100.0, 5.0])
    assert detect_racket_drop(elbow, trophy=0, contact=4) == 2


def test_racket_drop_none_without_room_or_anchors():
    elbow = np.arange(10.0)
    assert detect_racket_drop(elbow, trophy=4, contact=5) is None
    assert detect_racket_drop(elbow, trophy=None, contact=5) is None


def test_missing_trophy_propagates_to_racket_drop_only():
    s = synthetic_serve()
    s[A.TOSS_ARM_RAISE_PX][:] = nan
    assert detect_phases(s) == PhaseFrames(trophy=None, racket_drop=None, contact=45)


def test_phase_label_segments():
    phases = PhaseFrames(trophy=10, racket_drop=20, contact=30)
    assert phase_label(0, phases) == "Preparation"
    assert phase_label(10, phases) == "Trophy"
    assert phase_label(25, phases) == "Racket drop"
    assert phase_label(40, phases) == "Contact / follow-through"
    assert phase_label(40, PhaseFrames(contact=30)) == "Contact / follow-through"

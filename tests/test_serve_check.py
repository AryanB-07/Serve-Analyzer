"""The serve-shape check: what makes a clip a serve, and the reason given when it isn't."""

from dataclasses import replace

import numpy as np
import pytest

from evaluation import synthetic as sy
from serve_analyzer import angles as A
from serve_analyzer.config import AnalysisConfig
from serve_analyzer.errors import AnalysisError
from serve_analyzer.models import Hand
from serve_analyzer.phases import REJECTION_MESSAGES, serve_rejection
from serve_analyzer.pipeline import analyze_sequence, measure_detailed
from serve_analyzer.reference import load_ranges

FPS = 30.0
N = 60
CONTACT = 50


def _series(wrist_at_contact=1.0, toss_at_contact=-1.0, toss_peak_frame=35, toss_low=-1.5, toss_high=0.5):
    """Heights in torso lengths above the nose (torso = 100 px), shaped like a serve by default."""
    t = np.arange(N, dtype=float)
    wrist = np.where(t < CONTACT, -1.0 + (wrist_at_contact + 1.0) * t / CONTACT, wrist_at_contact)
    toss = np.interp(t, [0, toss_peak_frame, CONTACT, N], [toss_low, toss_high, toss_at_contact, toss_at_contact])
    return {
        A.WRIST_ELEVATION_PX: 100 * wrist,
        A.TOSS_WRIST_ELEVATION_PX: 100 * toss,
        A.NOSE_ELEVATION_PX: np.zeros(N),
        A.TORSO_LENGTH_PX: np.full(N, 100.0),
    }


def test_a_serve_shaped_clip_passes():
    assert serve_rejection(_series(), CONTACT, FPS) is None


@pytest.mark.parametrize(
    "kwargs, reason",
    [
        ({"wrist_at_contact": 0.1}, "wrist_not_above_head"),        # forehand/slice: wrist at head height
        ({"toss_at_contact": 0.9}, "both_hands_up"),                 # basketball shot, jumping jack
        ({"toss_peak_frame": 48, "toss_at_contact": 0.0}, "toss_too_late"),  # both arms swing up together
        ({"toss_low": 0.0, "toss_high": 0.4}, "no_toss_rise"),       # free hand never drops to toss
    ],
)
def test_each_missing_part_of_a_serve_has_its_own_reason(kwargs, reason):
    assert serve_rejection(_series(**kwargs), CONTACT, FPS) == reason
    assert reason in REJECTION_MESSAGES


def test_a_hidden_toss_arm_does_not_reject_a_serve():
    s = _series()
    s[A.TOSS_WRIST_ELEVATION_PX][:] = np.nan
    assert serve_rejection(s, CONTACT, FPS) is None


@pytest.mark.parametrize("cam", sy.CAMERAS, ids=lambda c: c.name)
@pytest.mark.parametrize("hand", [Hand.RIGHT, Hand.LEFT])
def test_synthetic_serves_pass_and_a_toss_without_a_swing_is_rejected_from_every_camera(cam, hand):
    spec = sy.ServeSpec(hand=hand)
    assert measure_detailed(sy.film(sy.make_serve(spec), cam), hand, AnalysisConfig()).rejection is None
    no_swing = sy.film(sy.make_serve(replace(spec, swing=False)), cam)
    assert measure_detailed(no_swing, hand, AnalysisConfig()).rejection is not None


def test_analysis_of_a_non_serve_fails_with_a_specific_reason():
    no_swing = sy.film(sy.make_serve(sy.ServeSpec(swing=False)), sy.CAMERAS[3])
    with pytest.raises(AnalysisError) as exc:
        analyze_sequence(no_swing, Hand.RIGHT, AnalysisConfig(), load_ranges())
    assert exc.value.code == "NOT_A_SERVE"
    assert str(exc.value).startswith("This doesn't look like a serve.")


def test_the_check_can_be_switched_off():
    no_swing = sy.film(sy.make_serve(sy.ServeSpec(swing=False)), sy.CAMERAS[3])
    cfg = AnalysisConfig(require_complete_serve=False)
    assert measure_detailed(no_swing, Hand.RIGHT, cfg).rejection is None

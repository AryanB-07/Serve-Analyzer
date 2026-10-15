"""Advanced mode's numbers (confidence, noise, camera error) and simple mode's plain feedback."""

import json
from dataclasses import replace

import pytest

from evaluation import synthetic as sy
from serve_analyzer import feedback
from serve_analyzer.angles import compute_series
from serve_analyzer.config import AnalysisConfig
from serve_analyzer.confidence import measurement_confidence
from serve_analyzer.models import Hand
from serve_analyzer.pipeline import analyze_sequence
from serve_analyzer.reference import load_ranges, ranges_to_dict
from serve_analyzer.view import _reliability_table

RANGES = ranges_to_dict(load_ranges())
MEASURED = {phase: list(by) for phase, by in RANGES.items()}


def _run(seq, camera_view=None, hand=Hand.RIGHT):
    return analyze_sequence(seq, hand, AnalysisConfig(), load_ranges(), camera_view=camera_view).result


def _side_on(noise=sy.NoiseModel()):
    return sy.film(sy.make_serve(sy.ServeSpec()), sy.CAMERAS[3], noise)


def test_every_measurement_at_a_found_phase_gets_numbers():
    result = _run(_side_on())
    for phase, metrics in MEASURED.items():
        if getattr(result.phases, phase) is None:
            assert phase not in result.confidence
            continue
        for metric in metrics:
            c = result.confidence[phase][metric]
            assert 0 <= c["visibility"] <= 1
            assert c["noise"] is None or c["noise"] >= 0
            assert c["camera_view_assumed"] is True


def test_without_a_camera_position_the_filming_guides_position_is_assumed():
    result = _run(_side_on())
    table = _reliability_table()["side_hitting"]
    assert result.confidence["trophy"]["front_knee_flexion"]["camera_error"] == pytest.approx(
        table["trophy.front_knee_flexion"], abs=0.05)


def test_a_given_camera_position_uses_its_own_error():
    result = _run(_side_on(), camera_view="front")
    c = result.confidence["trophy"]["front_knee_flexion"]
    assert c["camera_view_assumed"] is False
    assert c["camera_error"] == pytest.approx(_reliability_table()["front"]["trophy.front_knee_flexion"], abs=0.05)


def test_the_weakest_joint_sets_the_confidence():
    seq = _side_on()
    trophy = sy.make_serve(sy.ServeSpec()).phases.trophy
    before = _run(seq).confidence["trophy"]["front_knee_flexion"]["visibility"]
    seq.landmarks[trophy - 2:trophy + 3, 27, 2] = 0.31  # the front (left) ankle of a right-hander
    after = _run(seq).confidence["trophy"]["front_knee_flexion"]["visibility"]
    assert before > 0.9 and after == pytest.approx(0.31, abs=0.01)


def test_contact_height_needs_only_one_ankle():
    seq = _side_on()
    contact = sy.make_serve(sy.ServeSpec()).phases.contact
    seq.landmarks[contact - 2:contact + 3, 27, 2] = 0.1  # one ankle hidden
    c = measurement_confidence(seq, compute_series(seq, Hand.RIGHT), _run(seq).phases, Hand.RIGHT,
                               AnalysisConfig(), {"contact": ["wrist_height"]}, None)
    assert c["contact"]["wrist_height"]["visibility"] > 0.5


def test_more_tracking_jitter_means_more_noise():
    quiet = _run(_side_on(replace(sy.NoiseModel(), jitter_2d=0.002, jitter_2d_occluded=0.004)))
    shaky = _run(_side_on(replace(sy.NoiseModel(), jitter_2d=0.02, jitter_2d_occluded=0.04)))
    q, s = (r.confidence["trophy"]["trunk_tilt"]["noise"] for r in (quiet, shaky))
    assert s > 2 * q


def test_the_numbers_dont_change_the_measurements():
    seq = _side_on()
    result = _run(seq)
    plain = analyze_sequence(seq, Hand.RIGHT, AnalysisConfig(), load_ranges()).result
    assert result.metrics == plain.metrics and result.labels == plain.labels


# --- plain feedback -------------------------------------------------------------------------

def test_every_coaching_point_has_a_plain_version_without_numbers():
    assert set(feedback.PLAIN) == set(feedback.RULES)
    for text in feedback.PLAIN.values():
        assert not any(ch.isdigit() for ch in text), text


def test_feedback_carries_its_plain_version():
    result = _run(_side_on())
    assert result.feedback and all(f.plain for f in result.feedback)
    for f in result.feedback:
        if f.metric:
            assert not any(ch.isdigit() for ch in f.plain)
            assert any(ch.isdigit() for ch in f.text)  # the full version keeps its numbers
    assert json.loads(json.dumps(result.to_dict()))["feedback"][0]["plain"] == result.feedback[0].plain


def test_the_all_good_and_nothing_measured_messages_have_plain_versions():
    assert feedback.generate([])[0].plain == feedback.NOTHING_MEASURED


def test_a_phase_that_wasnt_found_comes_through_the_api_as_null():
    from serve_api.schemas import AnalysisResult

    result = _run(_side_on()).to_dict()
    result["confidence"].pop("racket_drop", None)  # as for a clip where it isn't detected
    model = AnalysisResult.model_validate({**result, "id": "a1", "video_url": "/v"})
    dumped = model.model_dump(mode="json")
    assert dumped["confidence"]["racket_drop"] is None
    AnalysisResult.model_validate(dumped)  # what the API sends validates as what it promises

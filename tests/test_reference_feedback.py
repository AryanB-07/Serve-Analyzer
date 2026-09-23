import json

import pytest

from serve_analyzer import feedback
from serve_analyzer.reference import Range, assess, classify, load_ranges, to_labels

RNG = Range(good=(10, 20), borderline=(5, 30))


@pytest.mark.parametrize(
    "value,expected",
    [
        (15, ("good", None)),
        (10, ("good", None)),
        (7, ("borderline", "low")),
        (25, ("borderline", "high")),
        (2, ("off", "low")),
        (31, ("off", "high")),
        (None, ("unknown", None)),
    ],
)
def test_classify(value, expected):
    assert classify(value, RNG) == expected


def test_packaged_ranges_load():
    table = load_ranges()
    assert "contact" in table and "elbow_angle" in table["contact"]


def test_invalid_ranges_rejected(tmp_path):
    path = tmp_path / "r.json"
    path.write_text(json.dumps({"contact": {"elbow_angle": {"good": [0, 50], "borderline": [10, 40]}}}))
    with pytest.raises(ValueError, match="contact.elbow_angle"):
        load_ranges(path)


def _metrics(**contact):
    return {"trophy": {}, "racket_drop": {}, "contact": contact}


def test_labels_and_feedback_prioritise_off_over_borderline():
    ranges = {
        "contact": {
            "elbow_angle": Range((160, 180), (145, 180)),
            "wrist_height": Range((1.3, 1.6), (1.15, 1.7)),
        },
        "trophy": {"front_knee_flexion": Range((50, 80), (35, 95))},
    }
    metrics = {
        "contact": {"elbow_angle": 120.0, "wrist_height": 1.2},
        "trophy": {"front_knee_flexion": 60.0},
    }
    assessments = assess(metrics, ranges)
    assert to_labels(assessments) == {
        "contact": {"elbow_angle": "off", "wrist_height": "borderline"},
        "trophy": {"front_knee_flexion": "good"},
    }
    points = feedback.generate(assessments)
    assert len(points) == 2
    assert points[0].startswith("Straighten your hitting arm")
    assert "1.20 body heights" in points[1]


def test_feedback_capped_at_max_points():
    ranges = load_ranges()
    bad = {
        phase: {metric: -1000.0 for metric in by_metric}
        for phase, by_metric in ranges.items()
    }
    points = feedback.generate(assess(bad, ranges))
    assert len(points) == feedback.MAX_POINTS


def test_feedback_all_good_and_nothing_measured():
    ranges = {"contact": {"elbow_angle": Range((160, 180), (145, 180))}}
    assert feedback.generate(assess(_metrics(elbow_angle=170.0), ranges)) == [feedback.ALL_GOOD]
    assert feedback.generate(assess(_metrics(), ranges)) == [feedback.NOTHING_MEASURED]

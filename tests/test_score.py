"""History's scores: worked out on the server with the same mapping as the results page.

frontend/src/test/score_vectors.json holds (value, range, score) cases from this module; the
frontend's tests check lib/score.ts gives the same answers, so the two can't drift apart.
Regenerate it with SCORE_VECTORS=write uv run pytest tests/test_score.py.
"""

import json
import os
from pathlib import Path

from serve_analyzer.reference import load_ranges, ranges_to_dict
from serve_analyzer.score import band_of, key_scores, score_for

VECTORS = Path(__file__).resolve().parents[1] / "frontend" / "src" / "test" / "score_vectors.json"
RANGES = ranges_to_dict(load_ranges())


def _cases():
    out = []
    for phase, by in RANGES.items():
        for metric, rng in by.items():
            b0, b1 = rng["borderline"]
            span = b1 - b0
            for i in range(-40, 141, 5):
                value = round(b0 + span * i / 100, 4)
                out.append({"phase": phase, "metric": metric, "value": value, "range": rng, "score": score_for(value, rng)})
    return out


def test_scores_match_the_shared_vectors_the_frontend_also_checks():
    cases = _cases()
    if os.getenv("SCORE_VECTORS") == "write":
        VECTORS.write_text(json.dumps(cases, indent=1) + "\n")
    assert json.loads(VECTORS.read_text()) == cases, "run SCORE_VECTORS=write uv run pytest tests/test_score.py"


def test_a_score_is_always_in_its_labels_band():
    for case in _cases():
        g0, g1 = case["range"]["good"]
        b0, b1 = case["range"]["borderline"]
        v = case["value"]
        label = "good" if g0 <= v <= g1 else "borderline" if b0 <= v <= b1 else "off"
        assert band_of(case["score"]) == label


def test_key_scores_average_the_scored_positions_and_skip_unreadable_ones():
    results = {
        "metrics": {"trophy": {"front_knee_flexion": 65.0, "back_knee_flexion": None, "trunk_tilt": 25.0},
                    "contact": {"elbow_angle": 170.0, "wrist_height": 1.45}},
        "ranges": RANGES,
        "quality": {"contact": {"wrist_height": "unreadable"}},
    }
    s = key_scores(results)
    assert s["key"]["front_knee_flexion"] == {"phase": "trophy", "value": 65.0, "score": 100, "band": "good"}
    assert s["key"]["back_knee_flexion"] is None and s["key"]["wrist_height"] is None
    assert s["overall"] == round((100 + s["key"]["trunk_tilt"]["score"] + s["key"]["elbow_angle"]["score"]) / 3)


def test_nothing_to_score_gives_no_overall():
    assert key_scores({"metrics": {}, "ranges": RANGES})["overall"] is None

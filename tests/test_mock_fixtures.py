"""The demo's data files (frontend/public/mock, from scripts/make_mock_fixtures.py) stay in step
with the pipeline: the frontend's tests read its reference ranges from them."""

import json
from pathlib import Path

from serve_analyzer.reference import load_ranges, ranges_to_dict

MOCK = Path(__file__).resolve().parents[1] / "frontend" / "public" / "mock"


def test_the_demo_uses_the_current_reference_ranges():
    expected = ranges_to_dict(load_ranges())
    for demo in ("demo-serve-1", "demo-serve-2"):
        ranges = json.loads((MOCK / demo / "result.json").read_text())["ranges"]
        trimmed = {phase: {m: r for m, r in by.items() if r is not None} for phase, by in ranges.items()}
        assert trimmed == expected, f"{demo}: run scripts/make_mock_fixtures.py"


def test_the_demo_has_the_advanced_mode_numbers():
    result = json.loads((MOCK / "demo-serve-1" / "result.json").read_text())
    assert result["confidence"]["trophy"]["front_knee_flexion"]["visibility"] is not None
    assert all(item["plain"] for item in result["feedback"])
    assert result["camera_view"] == "front"

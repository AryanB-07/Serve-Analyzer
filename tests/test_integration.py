import json
import urllib.error
from pathlib import Path

import cv2
import pytest

from serve_analyzer.config import AnalysisConfig
from serve_analyzer.pipeline import analyze
from serve_analyzer.pose import ensure_model

CLIP = Path(__file__).parent / "fixtures" / "sample_serve.mp4"

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def result_and_dir(tmp_path_factory):
    if not CLIP.exists():
        pytest.skip("sample clip not present")
    config = AnalysisConfig()
    try:
        ensure_model(config.model_variant, config.model_dir)
    except urllib.error.URLError as exc:
        pytest.skip(f"pose model unavailable: {exc}")
    out = tmp_path_factory.mktemp("results")
    return analyze(CLIP, "right", out, config), out


def test_phases_detected_in_plausible_frames(result_and_dir):
    result, _ = result_and_dir
    assert result.n_frames == 125
    assert 104 <= result.phases.trophy <= 118
    assert result.phases.contact >= 118
    assert result.phases.trophy < result.phases.contact


def test_results_json_written(result_and_dir):
    result, out = result_and_dir
    data = json.loads((out / "results.json").read_text())
    assert set(data) >= {"phases", "metrics", "labels", "feedback", "warnings"}
    assert data["phases"]["contact"] == result.phases.contact
    assert 1 <= len(data["feedback"]) <= 4
    assert data["metrics"]["trophy"]["front_knee_flexion"] is not None


def test_annotated_video_matches_input(result_and_dir):
    _, out = result_and_dir
    cap = cv2.VideoCapture(str(out / "annotated.mp4"))
    try:
        assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 125
        assert cap.get(cv2.CAP_PROP_FPS) == pytest.approx(25.0)
    finally:
        cap.release()

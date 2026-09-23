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
    stages: list[str] = []
    result = analyze(CLIP, "right", out, config, on_stage=stages.append)
    assert stages == ["extracting_pose", "analyzing", "rendering"]
    return result, out


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
    assert all("text" in item and "phase" in item for item in data["feedback"])
    assert data["metrics"]["trophy"]["front_knee_flexion"] is not None
    assert data["ranges"]["contact"]["elbow_angle"]["good"] == [160, 180]
    assert (data["width"], data["height"]) == (640, 480)


def test_frames_json_is_aligned_and_compact(result_and_dir):
    result, out = result_and_dir
    path = out / "frames.json"
    assert path.stat().st_size < 200_000
    frames = json.loads(path.read_text())
    n = frames["n_frames"]
    assert n == result.n_frames
    assert frames["phases"] == result.phases.as_dict()
    for kind in ("raw", "smoothed"):
        assert len(frames["landmarks"][kind]) == 13
        for track in frames["landmarks"][kind].values():
            assert len(track["x"]) == len(track["y"]) == n
    xs = [x for x in frames["landmarks"]["raw"]["nose"]["x"] if x is not None]
    assert xs and all(0 <= x <= 1 for x in xs)
    assert set(frames["series"]) == set(result.metrics["contact"])
    assert all(len(s) == n for s in frames["series"].values())


def test_playback_copy_and_thumbnail(result_and_dir):
    _, out = result_and_dir
    cap = cv2.VideoCapture(str(out / "playback.mp4"))
    try:
        assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 125
    finally:
        cap.release()
    thumb = cv2.imread(str(out / "thumbnail.jpg"))
    assert thumb is not None and thumb.shape[1] == 480


def test_annotated_video_matches_input(result_and_dir):
    _, out = result_and_dir
    cap = cv2.VideoCapture(str(out / "annotated.mp4"))
    try:
        assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 125
        assert cap.get(cv2.CAP_PROP_FPS) == pytest.approx(25.0)
    finally:
        cap.release()

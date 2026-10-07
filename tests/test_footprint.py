"""The API process must stay small enough for a 1 GB server: it never loads the video stack."""

import subprocess
import sys

HEAVY = ("mediapipe", "cv2", "scipy", "matplotlib")


def test_the_api_does_not_import_mediapipe_or_opencv():
    code = (
        "import sys, tempfile; from pathlib import Path\n"
        "from serve_api.app import create_app\nfrom serve_api.settings import Settings\n"
        "create_app(Settings(data_dir=Path(tempfile.mkdtemp())))\n"
        f"print(','.join(m for m in {HEAVY!r} if m in sys.modules))"
    )
    loaded = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert loaded == "", f"the API loaded {loaded}"


def test_the_package_still_exposes_analyze():
    import serve_analyzer

    assert callable(serve_analyzer.analyze)


def test_the_worker_process_does_not_load_mediapipe():
    code = "import sys, serve_api.worker; print('mediapipe' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "False"


def test_pose_in_a_subprocess_matches_pose_in_process():
    import numpy as np

    from serve_analyzer.config import AnalysisConfig
    from serve_analyzer.pose import ensure_model, extract_pose_in_subprocess, extract_pose_sequence
    from serve_analyzer.video import probe
    from tests.test_integration import CLIP

    info = probe(CLIP)
    model = ensure_model("heavy", AnalysisConfig().model_dir)
    here, there = extract_pose_sequence(info, model), extract_pose_in_subprocess(info, model)
    assert there.landmarks.shape == here.landmarks.shape
    np.testing.assert_allclose(there.landmarks, here.landmarks, equal_nan=True)
    np.testing.assert_allclose(there.world, here.world, equal_nan=True)


def test_releasing_memory_is_safe_everywhere():
    from serve_api.worker import release_memory

    release_memory()  # glibc: returns freed memory; elsewhere: does nothing

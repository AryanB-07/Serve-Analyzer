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

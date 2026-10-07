"""iPhones record HEVC (.mov), and portrait clips are stored sideways with a rotation tag.

The upload must decode upright and analyse like the original. Needs an ffmpeg with libx265
to make the test clip (CI installs one), so it's skipped elsewhere.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from serve_analyzer.models import Hand
from serve_analyzer.pipeline import analyze
from serve_analyzer.video import fourcc, probe

SAMPLE = Path(__file__).parent / "fixtures" / "sample_serve.mp4"


def _ffmpeg_with_x265() -> str | None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return None
    encoders = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    return ffmpeg if "libx265" in encoders else None


FFMPEG = _ffmpeg_with_x265()
pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(FFMPEG is None, reason="needs ffmpeg with libx265")]


@pytest.fixture(scope="module")
def iphone_clip(tmp_path_factory) -> Path:
    """The sample serve stored sideways as HEVC, with a tag that rotates it back upright."""
    folder = tmp_path_factory.mktemp("phone")
    sideways = folder / "sideways.mov"
    tagged = folder / "IMG_0001.MOV"
    subprocess.run([FFMPEG, "-loglevel", "error", "-i", str(SAMPLE), "-vf", "transpose=1", "-an",
                    "-c:v", "libx265", "-preset", "ultrafast", "-x265-params", "log-level=error",
                    "-tag:v", "hvc1", str(sideways)], check=True)
    subprocess.run([FFMPEG, "-loglevel", "error", "-display_rotation", "90", "-i", str(sideways),
                    "-c", "copy", str(tagged)], check=True)
    return tagged


def test_a_rotated_hevc_clip_decodes_upright(iphone_clip):
    original, phone = probe(SAMPLE), probe(iphone_clip)
    assert fourcc(iphone_clip) in ("hvc1", "hevc")
    assert (phone.width, phone.height) == (original.width, original.height)
    assert phone.frame_count == original.frame_count


def test_a_rotated_hevc_clip_analyses_like_the_original(iphone_clip, tmp_path):
    expected = analyze(SAMPLE, Hand.RIGHT, tmp_path / "original", render_video=False)
    result = analyze(iphone_clip, Hand.RIGHT, tmp_path / "phone", render_video=False)
    assert abs(result.phases.contact - expected.phases.contact) <= 2
    assert abs(result.phases.trophy - expected.phases.trophy) <= 2

"""Uploads in every supported container and the common codecs decode frame by frame.

The clips are made from the sample serve with ffmpeg, so this runs where ffmpeg is installed
(CI and the production image) and is skipped elsewhere.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from serve_analyzer.errors import VideoValidationError
from serve_analyzer.video import iter_frames, probe, probe_or_convert

SAMPLE = Path(__file__).parent / "fixtures" / "sample_serve.mp4"
FFMPEG = shutil.which("ffmpeg")


def _encoders() -> str:
    if FFMPEG is None:
        return ""
    return subprocess.run([FFMPEG, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout


ENCODERS = _encoders()
pytestmark = pytest.mark.skipif(FFMPEG is None, reason="needs ffmpeg")

# (file name, ffmpeg encoder, extra arguments). Each is what some phone, camera or app produces.
FORMATS = [
    ("h264.mp4", "libx264", ["-preset", "ultrafast"]),
    ("h264.mov", "libx264", ["-preset", "ultrafast"]),
    ("hevc.mov", "libx265", ["-preset", "ultrafast", "-tag:v", "hvc1", "-x265-params", "log-level=error"]),
    ("hevc.mp4", "libx265", ["-preset", "ultrafast", "-tag:v", "hvc1", "-x265-params", "log-level=error"]),
    ("vp9.webm", "libvpx-vp9", ["-deadline", "realtime", "-cpu-used", "8", "-b:v", "1M"]),
    ("vp8.webm", "libvpx", ["-deadline", "realtime", "-cpu-used", "8", "-b:v", "1M"]),
    ("h264.mkv", "libx264", ["-preset", "ultrafast"]),
    ("mjpeg.avi", "mjpeg", ["-q:v", "5"]),
    ("h264.3gp", "libx264", ["-preset", "ultrafast", "-profile:v", "baseline"]),
    ("h264.mts", "libx264", ["-preset", "ultrafast", "-f", "mpegts"]),
]


def _make(folder: Path, name: str, encoder: str, args: list[str]) -> Path:
    if encoder not in ENCODERS:
        pytest.skip(f"this ffmpeg has no {encoder}")
    out = folder / name
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-i", str(SAMPLE), "-an", "-c:v", encoder, *args, str(out)],
                   check=True)
    return out


@pytest.mark.parametrize("name, encoder, args", FORMATS, ids=[f[0] for f in FORMATS])
def test_each_format_decodes_every_frame(tmp_path, name, encoder, args):
    clip = _make(tmp_path, name, encoder, args)
    original = probe(SAMPLE)
    info = probe_or_convert(clip, tmp_path)
    assert info.path == clip  # read directly, no conversion needed
    assert (info.width, info.height) == (original.width, original.height)
    assert sum(1 for _ in iter_frames(clip)) == original.frame_count


def test_av1_is_converted_when_opencv_cannot_decode_it(tmp_path):
    clip = _make(tmp_path, "av1.mp4", "libaom-av1", ["-cpu-used", "8", "-row-mt", "1", "-b:v", "1M"])
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    info = probe_or_convert(clip, scratch)
    assert info.path.parent == scratch or info.path == clip  # converted unless OpenCV gains AV1
    assert sum(1 for _ in iter_frames(info.path)) == probe(SAMPLE).frame_count


def test_a_file_that_isnt_a_video_is_still_refused(tmp_path):
    junk = tmp_path / "notes.mp4"
    junk.write_bytes(b"this is not a video" * 100)
    with pytest.raises(VideoValidationError):
        probe_or_convert(junk, tmp_path)

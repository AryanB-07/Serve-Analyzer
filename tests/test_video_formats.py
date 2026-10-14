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


def test_stretched_pixels_are_made_square(tmp_path):
    from serve_analyzer.video import stream_fixes

    # HDV-style: stored 3/4 as wide, with a pixel aspect ratio that stretches it back.
    clip = _make(tmp_path, "hdv.mts", "libx264", ["-preset", "ultrafast", "-vf", "scale=iw*3/4:ih,setsar=4/3",
                                                    "-f", "mpegts"])
    assert any(f.startswith("scale=") for f in stream_fixes(clip))
    original, info = probe(SAMPLE), probe_or_convert(clip, tmp_path)
    assert info.path != clip
    assert info.width / info.height == pytest.approx(original.width / original.height, abs=0.02)


def test_interlaced_video_is_deinterlaced_to_full_frames(tmp_path):
    from serve_analyzer.video import stream_fixes

    # 60 fields a second, two per frame, as a 1080i camcorder records.
    clip = _make(tmp_path, "1080i.mts", "libx264", [
        "-preset", "ultrafast", "-vf", "fps=60,tinterlace=interleave_top,fieldorder=tff",
        "-flags", "+ildct+ilme", "-x264-params", "tff=1", "-f", "mpegts"])
    assert any(f.startswith("bwdif") for f in stream_fixes(clip))
    info = probe_or_convert(clip, tmp_path)
    assert info.fps == pytest.approx(60, abs=1)  # one full frame per field
    assert (info.width, info.height) == (probe(SAMPLE).width, probe(SAMPLE).height)


def test_ordinary_files_need_no_fixes(tmp_path):
    from serve_analyzer.video import stream_fixes

    assert stream_fixes(SAMPLE) == []
    assert stream_fixes(_make(tmp_path, "plain.mov", "libx264", ["-preset", "ultrafast"])) == []


# --- limits on size, frame rate and length -------------------------------------------------------

def _clip(folder: Path, name: str, vf: str, seconds: float = 1.0, rate: str | None = None) -> Path:
    out = folder / name
    rate_args = ["-r", rate] if rate else []
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-stream_loop", "-1", "-i", str(SAMPLE), "-t", str(seconds),
                    "-an", "-vf", vf, *rate_args, "-c:v", "libx264", "-preset", "ultrafast", str(out)], check=True)
    return out


@pytest.mark.parametrize("size, expected", [("3840:2160", (1920, 1080)), ("2160:3840", (1080, 1920))],
                         ids=["4k-landscape", "4k-portrait"])
def test_4k_is_scaled_down_to_fit_1920_keeping_its_orientation(tmp_path, size, expected):
    clip = _clip(tmp_path, "4k.mp4", f"scale={size}")
    info = probe_or_convert(clip, tmp_path)
    assert info.path != clip
    assert (info.width, info.height) == expected


def test_slow_motion_over_120_fps_is_reduced_to_120_keeping_time(tmp_path):
    clip = _clip(tmp_path, "240fps.mp4", "fps=240", seconds=2.0)
    assert probe(clip).fps == pytest.approx(240, abs=1)
    info = probe_or_convert(clip, tmp_path)
    assert info.fps == pytest.approx(120, abs=1)
    assert info.duration_s == pytest.approx(2.0, abs=0.1)


def test_120_fps_and_1080p_are_analysed_as_they_are(tmp_path):
    clip = _clip(tmp_path, "1080p120.mp4", "scale=1920:1080,fps=120")
    assert probe_or_convert(clip, tmp_path).path == clip


def test_a_long_file_is_refused_before_any_conversion(tmp_path):
    # 240 fps would need converting; the length is checked first, from the header alone.
    clip = _clip(tmp_path, "long.mp4", "scale=320:240,fps=240", seconds=20.0)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with pytest.raises(VideoValidationError) as exc:
        probe_or_convert(clip, scratch, max_duration_s=15)
    assert exc.value.code == "VIDEO_TOO_LONG"
    assert str(exc.value).startswith("Video is 20.0s long; the limit is 15s.")
    assert list(scratch.iterdir()) == []

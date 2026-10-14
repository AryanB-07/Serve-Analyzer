"""Parsing ffmpeg's stream description into the fixes and limits (no ffmpeg needed)."""

import pytest

from serve_analyzer.video import MAX_FPS, MAX_SIDE, _fixes, banner_duration

LINE = "  Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637661), yuv420p(tv, bt709, progressive), {size} [SAR 1:1 DAR 16:9], {fps} fps, {fps} tbr, 90k tbn (default)"
SCALE = f"scale={MAX_SIDE}:{MAX_SIDE}:force_original_aspect_ratio=decrease:force_divisible_by=2"


@pytest.mark.parametrize("size, fps, expected", [
    ("1920x1080", "30", []),
    ("1080x1920", "60", []),
    ("1920x1080", "120", []),
    ("1920x1080", "119.88", []),
    ("3840x2160", "30", [SCALE]),
    ("2160x3840", "30", [SCALE]),
    ("1280x720", "240", [f"fps={MAX_FPS:g}"]),
    ("3840x2160", "240", [f"fps={MAX_FPS:g}", SCALE]),
])
def test_big_or_fast_video_is_reduced(size, fps, expected):
    assert _fixes(LINE.format(size=size, fps=fps)) == expected


def test_interlaced_video_counts_its_doubled_frame_rate():
    line = LINE.format(size="1920x1080", fps="29.97").replace("progressive", "top first")
    assert _fixes(line) == ["bwdif=mode=send_field"]  # 59.94 fps after deinterlacing: fine
    fast = LINE.format(size="1920x1080", fps="100").replace("progressive", "top first")
    assert _fixes(fast) == ["bwdif=mode=send_field", f"fps={MAX_FPS:g}"]


def test_stretched_pixels_count_at_their_displayed_width():
    # HDV-style 2880x1080 with 2:1 pixels shows as 5760 wide: squared, then scaled down.
    line = LINE.format(size="2880x1080", fps="25").replace("SAR 1:1", "SAR 2:1")
    assert _fixes(line) == ["scale=trunc(iw*sar/2)*2:ih,setsar=1", SCALE]


@pytest.mark.parametrize("banner, seconds", [
    ("  Duration: 00:00:15.03, start: 0.000000, bitrate: 2111 kb/s", 15.03),
    ("  Duration: 01:02:03.50, start: 0.0", 3723.5),
    ("  Duration: N/A, start: -0.007000, bitrate: N/A", None),
    ("", None),
])
def test_the_header_duration_is_read(banner, seconds):
    assert banner_duration(banner) == (pytest.approx(seconds) if seconds else None)

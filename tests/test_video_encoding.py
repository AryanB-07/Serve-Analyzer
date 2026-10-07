"""Result videos must be H.264, the codec every browser plays, with every frame kept."""

import shutil

import cv2
import numpy as np
import pytest

from serve_analyzer.video import fourcc, make_browser_playable

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _mpeg4_clip(path, frames=30, size=(161, 121)):
    """An MPEG-4 Part 2 clip (what OpenCV writes on Linux), with odd dimensions on purpose."""
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 25, size)
    for i in range(frames):
        frame = np.full((size[1], size[0], 3), i * 8 % 255, np.uint8)
        writer.write(frame)
    writer.release()
    return path


@needs_ffmpeg
def test_mpeg4_is_reencoded_to_h264_keeping_every_frame(tmp_path):
    clip = _mpeg4_clip(tmp_path / "playback.mp4")
    assert fourcc(clip) != "avc1"
    make_browser_playable(clip)
    cap = cv2.VideoCapture(str(clip))
    assert fourcc(clip) in ("avc1", "h264")
    assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 30
    assert (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))) == (160, 120)
    assert not list(tmp_path.glob("*.h264.mp4"))


def test_without_ffmpeg_the_file_is_left_as_is(tmp_path, monkeypatch):
    clip = _mpeg4_clip(tmp_path / "playback.mp4")
    before = clip.read_bytes()
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert make_browser_playable(clip) == clip
    assert clip.read_bytes() == before

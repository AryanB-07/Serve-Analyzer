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


def test_a_missing_h264_writer_is_only_tried_once(tmp_path, monkeypatch):
    import serve_analyzer.video as video

    tried = []
    real_writer = cv2.VideoWriter

    def fake_writer(path, code, fps, size):
        name = "".join(chr((code >> 8 * i) & 0xFF) for i in range(4))
        tried.append(name)
        if name == "avc1":  # behave like OpenCV's Linux wheels
            return real_writer(str(path), cv2.VideoWriter_fourcc(*"XXXX"), fps, size)
        return real_writer(path, code, fps, size)

    monkeypatch.setattr(video, "_h264_writer_works", None)
    monkeypatch.setattr(video.cv2, "VideoWriter", fake_writer)
    for i in range(3):
        video.open_writer(tmp_path / f"{i}.mp4", 25, 64, 48).release()
    assert tried == ["avc1", "mp4v", "mp4v", "mp4v"]

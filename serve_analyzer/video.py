"""Video probing, validation, frame reading and writing."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np

from .errors import VideoValidationError
from .models import VideoInfo

__all__ = [
    "VideoValidationError", "iter_frames", "make_browser_playable", "open_browser_writer",
    "open_writer", "probe", "probe_or_convert", "validate", "write_playback_copy", "write_thumbnail",
]

log = logging.getLogger(__name__)
BROWSER_CODECS = {"avc1", "h264", "H264", "AVC1"}


def probe(path: str | Path) -> VideoInfo:
    path = Path(path)
    if not path.is_file():
        raise VideoValidationError(f"Video not found: {path}")
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise VideoValidationError(f"Could not open video: {path}")
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        # Take dimensions from a decoded frame: OpenCV applies rotation metadata
        # (portrait phone video) when decoding, but CAP_PROP_FRAME_* may not.
        ok, first = cap.read()
    finally:
        cap.release()
    if not ok or fps <= 0 or frame_count <= 0:
        raise VideoValidationError(f"Could not read frame rate or length of {path}")
    height, width = first.shape[:2]
    return VideoInfo(path, fps, frame_count, width, height)


def probe_or_convert(path: str | Path, scratch: str | Path) -> VideoInfo:
    """Probe a video, converting it to H.264 first if OpenCV can't decode it.

    OpenCV reads the usual formats (MP4, MOV, WebM, MKV, AVI, 3GP, MTS with H.264, HEVC,
    VP8/9, ProRes) but has no AV1 decoder. ffmpeg, when installed, converts anything it can
    read into ``scratch``, applying any rotation tag; the returned info points at that copy.
    """
    path = Path(path)
    try:
        return probe(path)
    except VideoValidationError as unreadable:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None or not path.is_file():
            raise
        converted = Path(scratch) / "converted.mp4"
        try:
            subprocess.run(
                [ffmpeg, "-y", "-loglevel", "error", "-i", str(path), "-an", "-c:v", "libx264",
                 "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-threads", "2",
                 "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", str(converted)],
                check=True, capture_output=True, timeout=600,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            raise unreadable from None
        log.info("%s couldn't be decoded directly; converted with ffmpeg", path.name)
        return probe(converted)


def validate(info: VideoInfo, max_duration_s: float, min_fps: float) -> None:
    if info.duration_s > max_duration_s:
        raise VideoValidationError(
            f"Video is {info.duration_s:.1f}s long; the limit is {max_duration_s:.0f}s. "
            "Trim it to a single serve.",
            code="VIDEO_TOO_LONG",
        )
    if info.fps < min_fps:
        raise VideoValidationError(
            f"Video is {info.fps:.1f} fps; at least {min_fps:.0f} fps is needed "
            "to capture the fast parts of the serve.",
            code="FPS_TOO_LOW",
        )


def iter_frames(path: str | Path) -> Iterator[np.ndarray]:
    """Yield BGR frames in order."""
    cap = cv2.VideoCapture(str(path))
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                return
            yield frame
    finally:
        cap.release()


# Whether OpenCV can write H.264 here: None until the first try. OpenCV's Linux wheels can't,
# and each failed attempt prints several ffmpeg errors, so it's tried once per process.
_h264_writer_works: bool | None = None


def open_writer(path: str | Path, fps: float, width: int, height: int) -> cv2.VideoWriter:
    """Open an MP4 writer, preferring H.264 (browser-playable) over MPEG-4 Part 2.

    Where H.264 isn't available, make_browser_playable re-encodes the result afterwards.
    """
    global _h264_writer_works
    codecs = ("avc1", "mp4v") if _h264_writer_works is not False else ("mp4v",)
    for codec in codecs:
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*codec), fps, (width, height))
        if codec == "avc1":
            _h264_writer_works = writer.isOpened()
        if writer.isOpened():
            return writer
        writer.release()
    raise RuntimeError(f"Could not open a video writer for {path}")


def fourcc(path: str | Path) -> str:
    cap = cv2.VideoCapture(str(path))
    try:
        code = int(cap.get(cv2.CAP_PROP_FOURCC))
    finally:
        cap.release()
    return "".join(chr((code >> 8 * i) & 0xFF) for i in range(4))


def make_browser_playable(path: str | Path) -> Path:
    """Make sure a video written by OpenCV plays in browsers.

    OpenCV's Linux wheels can't encode H.264, so open_writer falls back to MPEG-4 Part 2,
    which Chrome, Safari and Firefox won't play. In that case the file is re-encoded with
    ffmpeg (libx264), keeping every frame (frame i must still match pose frame i) and moving
    the index to the front so playback starts before the whole file has downloaded.
    """
    path = Path(path)
    if fourcc(path) in BROWSER_CODECS:
        return path
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        log.warning("%s isn't H.264 and ffmpeg isn't installed; browsers may not play it", path.name)
        return path
    tmp = path.with_name(f"{path.stem}.h264{path.suffix}")
    try:
        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(path), "-an", *EVEN_SIZE, *X264_ARGS,
             # Keep every frame (frame i must still match pose frame i).
             "-fps_mode", "passthrough", str(tmp)],
            check=True, capture_output=True, timeout=600,
        )
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


# Shared by both H.264 paths. x264's memory grows with its thread count: all cores took
# 935 MB on a 1080p clip, two take about 420 MB at the same speed on a 2-vCPU server.
X264_ARGS = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
             "-threads", "2", "-movflags", "+faststart"]
# yuv420p needs even dimensions; odd ones lose one pixel row or column.
EVEN_SIZE = ["-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2"]


class FfmpegWriter:
    """Encodes frames straight to browser-playable H.264 by piping them into ffmpeg.

    Compared with writing MPEG-4 Part 2 through OpenCV and re-encoding it, this compresses
    once instead of twice: files about 20% smaller at better quality, no intermediate file,
    and slightly less memory. Every frame written is one output frame, at a constant ``fps``.
    """

    def __init__(self, ffmpeg: str, path: Path, fps: float, width: int, height: int) -> None:
        self.path = path
        self._proc = subprocess.Popen(
            [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
             "-s", f"{width}x{height}", "-r", f"{fps:.6f}", "-i", "-", "-an",
             *EVEN_SIZE, *X264_ARGS, str(path)],
            stdin=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    def write(self, frame: np.ndarray) -> None:
        try:
            self._proc.stdin.write(np.ascontiguousarray(frame).tobytes())
        except BrokenPipeError:
            self.release()  # raises with ffmpeg's error message

    def release(self) -> None:
        if self._proc.stdin and not self._proc.stdin.closed:
            try:
                self._proc.stdin.close()
            except BrokenPipeError:
                pass
        err = self._proc.stderr.read() if self._proc.stderr else b""
        self._proc.wait(timeout=600)
        if self._proc.returncode != 0:
            raise RuntimeError(f"ffmpeg couldn't encode {self.path.name}: {err.decode(errors='replace').strip()}")


def open_browser_writer(path: str | Path, fps: float, width: int, height: int):
    """A writer whose output browsers can play: ffmpeg's H.264 when installed, otherwise
    OpenCV's writer (H.264 on macOS; elsewhere make_browser_playable warns)."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is not None:
        return FfmpegWriter(ffmpeg, Path(path), fps, width, height)
    return open_writer(path, fps, width, height)


def write_playback_copy(src: str | Path, dst: str | Path, fps: float) -> Path:
    """Re-encode so browsers can play it and frame i matches pose frame i."""
    dst = Path(dst)
    writer = None
    try:
        for frame in iter_frames(src):
            if writer is None:
                h, w = frame.shape[:2]
                writer = open_browser_writer(dst, fps, w, h)
            writer.write(frame)
    finally:
        if writer is not None:
            writer.release()
    return make_browser_playable(dst)


def write_thumbnail(src: str | Path, frame_index: int, dst: str | Path, width: int = 480) -> Path:
    dst = Path(dst)
    chosen = None
    for i, frame in enumerate(iter_frames(src)):
        chosen = frame
        if i >= frame_index:
            break
    if chosen is None:
        raise VideoValidationError(f"Could not read a frame from {src}")
    h, w = chosen.shape[:2]
    thumb = cv2.resize(chosen, (width, round(h * width / w)), interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(dst), thumb, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return dst

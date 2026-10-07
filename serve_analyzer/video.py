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
    "VideoValidationError", "iter_frames", "make_browser_playable", "open_writer", "probe",
    "validate", "write_playback_copy", "write_thumbnail",
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


def open_writer(path: str | Path, fps: float, width: int, height: int) -> cv2.VideoWriter:
    """Open an MP4 writer, preferring H.264 (browser-playable) over MPEG-4 Part 2."""
    for codec in ("avc1", "mp4v"):
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*codec), fps, (width, height))
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
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(path), "-an",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
             # x264's memory grows with its thread count: all cores took 935 MB on a 1080p
             # clip, two take 446 MB at the same speed on a 2-vCPU server.
             "-threads", "2",
             # yuv420p needs even dimensions; odd ones lose one pixel row or column.
             "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
             "-fps_mode", "passthrough", "-movflags", "+faststart", str(tmp)],
            check=True, capture_output=True, timeout=600,
        )
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def write_playback_copy(src: str | Path, dst: str | Path, fps: float) -> Path:
    """Re-encode so browsers can play it and frame i matches pose frame i."""
    dst = Path(dst)
    writer = None
    try:
        for frame in iter_frames(src):
            if writer is None:
                h, w = frame.shape[:2]
                writer = open_writer(dst, fps, w, h)
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

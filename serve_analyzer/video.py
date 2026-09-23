"""Video probing, validation, frame reading and writing."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np

from .models import VideoInfo


class VideoValidationError(ValueError):
    """The input video cannot be analysed (unreadable, too long, too slow)."""


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
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    finally:
        cap.release()
    if fps <= 0 or frame_count <= 0:
        raise VideoValidationError(f"Could not read frame rate or length of {path}")
    return VideoInfo(path, fps, frame_count, width, height)


def validate(info: VideoInfo, max_duration_s: float, min_fps: float) -> None:
    if info.duration_s > max_duration_s:
        raise VideoValidationError(
            f"Video is {info.duration_s:.1f}s long; the limit is {max_duration_s:.0f}s. "
            "Trim it to a single serve."
        )
    if info.fps < min_fps:
        raise VideoValidationError(
            f"Video is {info.fps:.1f} fps; at least {min_fps:.0f} fps is needed "
            "to capture the fast parts of the serve."
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

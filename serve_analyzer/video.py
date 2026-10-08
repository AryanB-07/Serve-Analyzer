"""Video probing, validation, frame reading and writing."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from collections.abc import Iterator
from fractions import Fraction
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
    # Some files (e.g. WebM recorded in a browser) have no usable length in their header, and
    # OpenCV returns nonsense such as -2.7e17. Over a day of video counts as unknown too, so
    # probe_or_convert rewrites the file with a proper header instead of misjudging its length.
    if not ok or fps <= 0 or frame_count <= 0 or frame_count > fps * 86_400:
        raise VideoValidationError(f"Could not read frame rate or length of {path}")
    height, width = first.shape[:2]
    return VideoInfo(path, fps, frame_count, width, height)


def stream_fixes(path: str | Path, ffmpeg: str | None = None) -> list[str]:
    """ffmpeg filters a video needs before analysis, from its stream description.

    - Interlaced video (camcorders' 1080i) carries two half-frames per frame taken 1/50 or
      1/60 s apart, which smears fast motion into comb patterns. It's deinterlaced into one
      full frame per field ("bwdif" in field mode), which also doubles the frame rate.
    - Non-square pixels (HDV's 1440x1080 shown as 1920x1080) make the person look squeezed,
      which would distort every angle; they're scaled to square pixels.
    HDR (iPhone HLG, HDR10) is decoded as it is for now: tone-mapping synthetic HLG test
    footage didn't bring it closer to the original, so it needs tuning on real iPhone clips.
    """
    ffmpeg = ffmpeg or shutil.which("ffmpeg")
    if ffmpeg is None:
        return []
    try:
        banner = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True,
                                text=True, timeout=60).stderr
    except (OSError, subprocess.TimeoutExpired):
        return []
    line = next((ln for ln in banner.splitlines() if "Video:" in ln and "attached pic" not in ln), "")
    fixes = []
    if re.search(r"\b(top|bottom) (coded )?first\b", line):
        fixes.append("bwdif=mode=send_field")
    sar = re.search(r"SAR (\d+):(\d+)", line)
    if sar and int(sar[2]) and abs(Fraction(int(sar[1]), int(sar[2])) - 1) > Fraction(1, 100):
        fixes.append("scale=trunc(iw*sar/2)*2:ih,setsar=1")
    return fixes


def probe_or_convert(path: str | Path, scratch: str | Path) -> VideoInfo:
    """Probe a video, converting it with ffmpeg first when that's needed to analyse it.

    OpenCV reads the usual formats (MP4, MOV, WebM, MKV, AVI, 3GP, MTS with H.264, HEVC,
    VP8/9, ProRes) but has no AV1 decoder, and it ignores interlacing and non-square pixels
    (see ``stream_fixes``). In those cases ffmpeg, when installed, converts the video into
    ``scratch`` (also applying any rotation tag) and the returned info points at that copy.
    """
    path = Path(path)
    ffmpeg = shutil.which("ffmpeg")
    fixes = stream_fixes(path, ffmpeg) if ffmpeg and path.is_file() else []
    unreadable: VideoValidationError | None = None
    if not fixes:
        try:
            return probe(path)
        except VideoValidationError as exc:
            if ffmpeg is None or not path.is_file():
                raise
            unreadable = exc
    converted = Path(scratch) / "converted.mp4"
    try:
        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(path), "-an", "-map", "0:v:0",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-threads", "2",
             "-vf", ",".join([*fixes, "scale=trunc(iw/2)*2:trunc(ih/2)*2"]), str(converted)],
            check=True, capture_output=True, timeout=600,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        if unreadable is not None:
            raise unreadable from None
        return probe(path)  # the fixes failed; analyse the original as it is
    log.info("%s converted with ffmpeg (%s)", path.name, ", ".join(fixes) or "OpenCV couldn't decode it")
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

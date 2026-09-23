"""Pose extraction with the MediaPipe Tasks PoseLandmarker."""

from __future__ import annotations

import os
import tempfile
import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    PoseLandmarker,
    PoseLandmarkerOptions,
    RunningMode,
)

from .landmarks import NUM_LANDMARKS
from .models import PoseSequence, VideoInfo
from .video import iter_frames

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_{variant}/float16/latest/pose_landmarker_{variant}.task"
)


def ensure_model(variant: str, model_dir: Path) -> Path:
    """Return the local model path, downloading it on first use."""
    path = model_dir / f"pose_landmarker_{variant}.task"
    if path.exists():
        return path
    model_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=model_dir, suffix=".part")
    os.close(fd)
    try:
        urllib.request.urlretrieve(MODEL_URL.format(variant=variant), tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return path


def extract_pose_sequence(info: VideoInfo, model_path: Path) -> PoseSequence:
    """Run the landmarker on every frame.

    Frames with no detected person get NaN coordinates and zero visibility.
    """
    options = PoseLandmarkerOptions(
        base_options=BaseOptions(
            model_asset_path=str(model_path), delegate=BaseOptions.Delegate.CPU
        ),
        running_mode=RunningMode.VIDEO,
        num_poses=1,
    )
    rows: list[np.ndarray] = []
    last_ts = -1
    with PoseLandmarker.create_from_options(options) as landmarker:
        for i, frame in enumerate(iter_frames(info.path)):
            # VIDEO mode requires strictly increasing integer timestamps.
            ts = max(round(i * 1000 / info.fps), last_ts + 1)
            last_ts = ts
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = landmarker.detect_for_video(
                mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts
            )
            rows.append(_to_pixel_array(result.pose_landmarks, info.width, info.height))

    landmarks = np.stack(rows) if rows else np.empty((0, NUM_LANDMARKS, 3))
    return PoseSequence(landmarks, info.fps, info.width, info.height)


def _to_pixel_array(poses: list, width: int, height: int) -> np.ndarray:
    out = np.full((NUM_LANDMARKS, 3), np.nan)
    out[:, 2] = 0.0
    if not poses:
        return out
    for j, lm in enumerate(poses[0]):
        out[j] = (lm.x * width, lm.y * height, lm.visibility)
    return out

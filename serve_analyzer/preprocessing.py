"""Landmark cleaning: visibility masking, short-gap interpolation, smoothing."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
from scipy.signal import savgol_filter

from .models import PoseSequence


def mask_low_visibility(landmarks: np.ndarray, threshold: float) -> np.ndarray:
    """Return a copy with x, y set to NaN wherever visibility < threshold."""
    out = landmarks.copy()
    low = out[..., 2] < threshold
    out[low, 0] = np.nan
    out[low, 1] = np.nan
    return out


def nan_runs(series: np.ndarray) -> list[tuple[int, int]]:
    """Half-open [start, end) index ranges of consecutive NaNs."""
    isnan = np.isnan(series).astype(np.int8)
    edges = np.diff(np.concatenate(([0], isnan, [0])))
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def interpolate_gaps(series: np.ndarray, max_gap: int) -> np.ndarray:
    """Linearly fill interior NaN runs of length <= max_gap.

    Runs touching either end are left alone: there is no second anchor
    point, so filling them would mean extrapolating motion we never saw.
    """
    out = series.copy()
    n = len(out)
    for start, end in nan_runs(out):
        if start == 0 or end == n or end - start > max_gap:
            continue
        left, right = out[start - 1], out[end]
        out[start:end] = np.interp(np.arange(start, end), [start - 1, end], [left, right])
    return out


def window_frames(window_ms: float, fps: float, polyorder: int) -> int:
    """Convert a smoothing window in ms to an odd frame count valid for savgol."""
    n = max(round(window_ms * fps / 1000), polyorder + 2)
    return n if n % 2 == 1 else n + 1


def smooth_series(series: np.ndarray, window: int, polyorder: int) -> np.ndarray:
    """Savitzky-Golay filter applied to each contiguous non-NaN segment.

    Segments shorter than the window are left unsmoothed.
    """
    out = series.copy()
    valid = ~np.isnan(series)
    edges = np.diff(np.concatenate(([0], valid.astype(np.int8), [0])))
    for start, end in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
        if end - start >= window:
            out[start:end] = savgol_filter(series[start:end], window, polyorder)
    return out


def clean(
    seq: PoseSequence,
    visibility_threshold: float,
    max_gap_frames: int,
    smoothing_window_ms: float | None,
    polyorder: int = 2,
) -> PoseSequence:
    """Mask, interpolate and (if a window is given) smooth every landmark trajectory."""
    lm = mask_low_visibility(seq.landmarks, visibility_threshold)
    window = (
        window_frames(smoothing_window_ms, seq.fps, polyorder) if smoothing_window_ms else None
    )
    for j in range(lm.shape[1]):
        for c in (0, 1):
            s = interpolate_gaps(lm[:, j, c], max_gap_frames)
            if window is not None:
                s = smooth_series(s, window, polyorder)
            lm[:, j, c] = s
    return replace(seq, landmarks=lm)

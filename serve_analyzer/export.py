"""Per-frame data export (frames.json) for interactive frontends.

Column-oriented: one array per landmark coordinate and per metric, so keys
are not repeated for every frame and arrays can be charted directly.
Coordinates are normalised to [0, 1] of the (rotation-corrected) frame.
Missing values are None.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from . import angles as A
from .landmarks import DRAWN_LANDMARKS
from .models import PhaseFrames, PoseSequence

FRAMES_SCHEMA_VERSION = 1
COORD_DECIMALS = 4
VISIBILITY_DECIMALS = 2
SERIES_DECIMALS = {A.WRIST_HEIGHT: 3}
DEFAULT_SERIES_DECIMALS = 1


def _column(values: np.ndarray, decimals: int) -> list[float | None]:
    return [None if math.isnan(v) else round(float(v), decimals) for v in values]


def _tracks(seq: PoseSequence, with_visibility: bool) -> dict[str, dict[str, list[float | None]]]:
    out = {}
    for name, j in DRAWN_LANDMARKS.items():
        track = {
            "x": _column(seq.landmarks[:, j, 0] / seq.width, COORD_DECIMALS),
            "y": _column(seq.landmarks[:, j, 1] / seq.height, COORD_DECIMALS),
        }
        if with_visibility:
            track["v"] = _column(seq.landmarks[:, j, 2], VISIBILITY_DECIMALS)
        out[name] = track
    return out


def build_frames_payload(
    raw: PoseSequence, smoothed: PoseSequence, series: A.Series, phases: PhaseFrames
) -> dict[str, Any]:
    """``raw`` is the unfiltered detector output (with visibility); ``smoothed`` is
    after masking, gap filling and smoothing."""
    return {
        "schema_version": FRAMES_SCHEMA_VERSION,
        "fps": raw.fps,
        "n_frames": raw.n_frames,
        "width": raw.width,
        "height": raw.height,
        "phases": phases.as_dict(),
        "landmarks": {
            "raw": _tracks(raw, with_visibility=True),
            "smoothed": _tracks(smoothed, with_visibility=False),
        },
        "series": {
            name: _column(series[name], SERIES_DECIMALS.get(name, DEFAULT_SERIES_DECIMALS))
            for name in A.METRIC_NAMES
        },
    }

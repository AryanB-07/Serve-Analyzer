"""Metric values at each detected phase."""

from __future__ import annotations

import math

from . import angles as A
from .models import Metrics, PhaseFrames

PHASE_NAMES = ["trophy", "racket_drop", "contact"]


def compute_metrics(series: A.Series, phases: PhaseFrames) -> Metrics:
    """{phase: {metric: value}}; None where the phase or the value is missing."""
    out: Metrics = {}
    for phase in PHASE_NAMES:
        frame = getattr(phases, phase)
        out[phase] = {}
        for name in A.METRIC_NAMES:
            value = None if frame is None else float(series[name][frame])
            out[phase][name] = None if value is None or math.isnan(value) else round(value, 3)
    return out

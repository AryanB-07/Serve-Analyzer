"""Reference ranges and good/borderline/off labelling."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Literal

from .models import Labels, Metrics, Ranges

Status = Literal["good", "borderline", "off", "unknown"]
Direction = Literal["low", "high"]


@dataclass(frozen=True)
class Range:
    good: tuple[float, float]
    borderline: tuple[float, float]


RangeTable = dict[str, dict[str, Range]]


@dataclass(frozen=True)
class Assessment:
    phase: str
    metric: str
    value: float | None
    status: Status
    direction: Direction | None
    range: Range


def load_ranges(path: Path | None = None) -> RangeTable:
    """Load ranges from ``path``, or the packaged defaults if None."""
    if path is None:
        text = resources.files("serve_analyzer").joinpath("data/reference_ranges.json").read_text()
        source = "packaged reference_ranges.json"
    else:
        text, source = Path(path).read_text(), str(path)
    raw = json.loads(text)

    table: RangeTable = {}
    for phase, metrics in raw.items():
        if phase.startswith("_"):
            continue
        table[phase] = {}
        for metric, spec in metrics.items():
            good, border = tuple(spec["good"]), tuple(spec["borderline"])
            if not (border[0] <= good[0] <= good[1] <= border[1]):
                raise ValueError(
                    f"{source}: {phase}.{metric} needs borderline_lo <= good_lo <= good_hi "
                    f"<= borderline_hi, got good={list(good)} borderline={list(border)}"
                )
            table[phase][metric] = Range(good, border)
    return table


def classify(value: float | None, rng: Range) -> tuple[Status, Direction | None]:
    if value is None:
        return "unknown", None
    lo, hi = rng.good
    if lo <= value <= hi:
        return "good", None
    direction: Direction = "low" if value < lo else "high"
    b_lo, b_hi = rng.borderline
    return ("borderline" if b_lo <= value <= b_hi else "off"), direction


def assess(metrics: Metrics, ranges: RangeTable) -> list[Assessment]:
    """Assess every metric that has a reference range."""
    out = []
    for phase, by_metric in ranges.items():
        for metric, rng in by_metric.items():
            value = metrics.get(phase, {}).get(metric)
            status, direction = classify(value, rng)
            out.append(Assessment(phase, metric, value, status, direction, rng))
    return out


def to_labels(assessments: list[Assessment]) -> Labels:
    labels: Labels = {}
    for a in assessments:
        labels.setdefault(a.phase, {})[a.metric] = a.status
    return labels


def ranges_to_dict(ranges: RangeTable) -> Ranges:
    return {
        phase: {m: {"good": list(r.good), "borderline": list(r.borderline)} for m, r in by.items()}
        for phase, by in ranges.items()
    }

"""Simple mode's 0-100 scores, worked out once here so History can sort and filter by them.

The same mapping as frontend/src/lib/score.ts (shared test vectors keep them in step):

    100 ............ 80 ............ 50 ............ 0
    centre of good   edge of good    edge of borderline   one borderline-width beyond

so a score always falls in its label's band: good 80-100, borderline 50-79, needs work 0-49.
"""

from __future__ import annotations

from typing import Any

# The five key positions on the results page, each scored at its key phase (lib/metricInfo.ts).
KEY_POSITIONS: dict[str, str] = {
    "front_knee_flexion": "trophy",
    "back_knee_flexion": "trophy",
    "trunk_tilt": "trophy",
    "elbow_angle": "contact",
    "wrist_height": "contact",
}
BANDS = ("good", "borderline", "off")


def _status(value: float, good: list[float], borderline: list[float]) -> str:
    if good[0] <= value <= good[1]:
        return "good"
    if borderline[0] <= value <= borderline[1]:
        return "borderline"
    return "off"


def _raw(value: float, good: list[float], borderline: list[float]) -> float:
    g0, g1 = good
    b0, b1 = borderline
    if g0 <= value <= g1:
        half = (g1 - g0) / 2
        return 80 + 20 * (1 - abs(value - (g0 + g1) / 2) / half) if half > 0 else 100
    below = value < g0
    edge = g0 if below else g1
    band = g0 - b0 if below else b1 - g1
    distance = abs(value - edge)
    if band > 0 and distance <= band:
        return 80 - 30 * distance / band
    scale = band if band > 0 else max(1e-9, g1 - g0)
    beyond = distance - band if band > 0 else distance
    return max(0.0, 50 - 50 * beyond / scale)


def _round(x: float) -> int:
    """Round half up, like JavaScript's Math.round (Python's round() goes to even)."""
    import math

    return math.floor(x + 0.5)


def score_for(value: float | None, rng: dict | None) -> int | None:
    """0-100 for ``value`` against ``rng`` ({"good": [lo, hi], "borderline": [lo, hi]})."""
    if value is None or not rng:
        return None
    status = _status(value, rng["good"], rng["borderline"])
    low, high = {"good": (80, 100), "borderline": (50, 79), "off": (0, 49)}[status]
    return min(high, max(low, _round(_raw(value, rng["good"], rng["borderline"]))))


def band_of(score: int) -> str:
    return "good" if score >= 80 else "borderline" if score >= 50 else "off"


def key_scores(results: dict[str, Any]) -> dict[str, Any]:
    """{"overall": int | None, "key": {metric: {phase, value, score, band} | None}} from a
    results.json dict. Measurements the camera position can't read aren't scored."""
    quality = results.get("quality") or {}
    key: dict[str, Any] = {}
    for metric, phase in KEY_POSITIONS.items():
        value = (results.get("metrics", {}).get(phase) or {}).get(metric)
        rng = (results.get("ranges", {}).get(phase) or {}).get(metric)
        unreadable = (quality.get(phase) or {}).get(metric) == "unreadable"
        score = None if unreadable else score_for(value, rng)
        key[metric] = None if score is None else {"phase": phase, "value": value, "score": score, "band": band_of(score)}
    present = [k["score"] for k in key.values() if k]
    overall = _round(sum(present) / len(present)) if present else None
    return {"overall": overall, "key": key}

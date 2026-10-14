"""How well the camera view can be told from the landmarks, and which measurements each view supports.

    python -m evaluation.views            # writes evaluation/reports/views_<time>.md
    python -m evaluation.views table      # rewrites serve_analyzer/data/view_reliability.json

Three parts:
1. Synthetic: every serve spec x every rig camera, with the stance fixed at the rig's 80°
   (the old assumption) and with it varied over the range real players show.
2. Real: the 26 labelled clips (cached landmarks; `python -m evaluation.real fetch` first).
3. Reliability: for each rig view, each measurement's error against the exact 3D value at the
   true phase frame. A measurement is reliable from a view if its 90th-percentile error is
   within 10° (0.1 body heights for wrist height).

Each estimator variant takes the body's turn at one moment and subtracts a fixed stance turn.
For the real clips that turn is fitted leaving each player out, so no clip is judged with a
number tuned on itself.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import numpy as np

from evaluation import synthetic as sy
from evaluation.real import load_clips, load_pose
from serve_analyzer import angles as A
from serve_analyzer.models import Hand, PhaseFrames
from serve_analyzer.phases import detect_contact
from serve_analyzer.view import CATEGORIES, STANCE_TURN_DEG, body_angle, categorise, set_position_window

REPORTS = Path(__file__).parent / "reports"
LABELS = json.loads((Path(__file__).parent / "labels" / "real_clips.json").read_text())["clips"]
ORDER = ["behind", "behind-diagonal", "side-on", "front-diagonal", "front"]
CENTRES = {"behind": 0.0, "front": 180.0}
REAL_STANCE_TURNS = (-20.0, 10.0, 40.0, 70.0, 90.0)  # the spread seen on the real players
TARGETS = {"side-on detection": 0.95, "side": 0.95, "category": 0.85}
PHASE_METRICS = {
    "trophy": ["front_knee_flexion", "back_knee_flexion", "elbow_angle", "trunk_tilt"],
    "racket_drop": ["elbow_angle", "trunk_tilt"],
    "contact": ["elbow_angle", "wrist_height", "front_knee_flexion", "trunk_tilt"],
}


def wrap(deg: float) -> float:
    return (deg + 180) % 360 - 180


def true_angle(category: str, side: str | None) -> float:
    """A label's centre angle (hand-relative): what the real clips are compared against."""
    if category in CENTRES:
        return CENTRES[category]
    base = {"behind-diagonal": 45.0, "side-on": 90.0, "front-diagonal": 135.0}[category]
    return base if side == "hitting" else 360 - base


def rig_truth(cam: sy.Camera, hand: Hand) -> tuple[float, str, str | None]:
    az = cam.azimuth % 360 if hand is Hand.RIGHT else (-cam.azimuth) % 360
    name, side, _ = categorise(az)
    return az, name, side


def moment(seq, hand, contact, which: str, trophy: int | None = None) -> tuple[int, int]:
    n = seq.n_frames
    if which == "set":
        return set_position_window(seq, hand, contact)
    if which == "trophy" and trophy is not None:
        return max(0, trophy - 2), min(n, trophy + 3)
    if which == "contact" and contact is not None:
        return max(0, contact - 1), min(n, contact + 2)
    return set_position_window(seq, hand, contact)


# --- scoring ------------------------------------------------------------------------------------

def score(rows: list[dict]) -> dict[str, float]:
    """rows: dicts with true/pred category and side. Returns the three target rates."""
    if not rows:
        return {}
    side_on = np.mean([(r["true"] == "side-on") == (r["pred"] == "side-on") for r in rows])
    sided = [r for r in rows if r["true_side"] is not None]
    side = np.mean([r["pred_side"] == r["true_side"] for r in sided]) if sided else float("nan")
    category = np.mean([r["true"] == r["pred"] for r in rows])
    return {"side-on detection": float(side_on), "side": float(side), "category": float(category)}


def confusion(rows: list[dict]) -> str:
    counts = Counter((r["true"], r["pred"]) for r in rows)
    preds = ORDER + (["none"] if any(r["pred"] == "none" for r in rows) else [])
    lines = ["| true \\ predicted | " + " | ".join(preds) + " |", "|---|" + "---|" * len(preds)]
    for t in ORDER:
        if any(r["true"] == t for r in rows):
            lines.append(f"| **{t}** | " + " | ".join(str(counts[(t, p)] or "·") for p in preds) + " |")
    return "\n".join(lines)


def targets_line(s: dict[str, float]) -> str:
    return " · ".join(f"{k} **{v:.0%}** ({'meets' if v >= TARGETS[k] else 'misses'} {TARGETS[k]:.0%})"
                      for k, v in s.items())


# --- 1. synthetic ---------------------------------------------------------------------------------

def synthetic(stance_turns: tuple[float, ...], which: str, turn: float) -> tuple[list[dict], list[float], float]:
    rows, errors, timings = [], [], []
    for cam in sy.CAMERAS:
        for base in sy.SERVE_SPECS:
            for st in stance_turns:
                spec = replace(base, stance_turn_deg=st)
                serve = sy.make_serve(spec)
                seq = sy.film(serve, cam)
                series = A.compute_series(seq, spec.hand)
                contact = detect_contact(series[A.WRIST_ELEVATION_PX])
                t0 = time.perf_counter()
                a, b = moment(seq, spec.hand, contact, which, serve.phases.trophy)
                bt = body_angle(seq, spec.hand, slice(a, b))
                timings.append(time.perf_counter() - t0)
                az, true_cat, true_side = rig_truth(cam, spec.hand)
                if bt.angle_deg is None:
                    rows.append({"true": true_cat, "true_side": true_side, "pred": "none", "pred_side": None})
                    continue
                est = (bt.angle_deg - turn) % 360
                cat, side, _ = categorise(est)
                errors.append(abs(wrap(est - az)))
                rows.append({"true": true_cat, "true_side": true_side, "pred": cat, "pred_side": side})
    return rows, errors, float(np.median(timings) * 1000)


# --- 2. real ----------------------------------------------------------------------------------------

def real_category(view: str) -> str:
    return "front" if view.startswith("front (") else view


def real_turns(which: str) -> list[dict]:
    """Per clip: the body angle at ``which``, and what stance turn its label implies."""
    out = []
    for clip in load_clips():
        seq = load_pose(clip)
        series = A.compute_series(seq, clip.hand)
        contact = clip.contact if clip.contact is not None else detect_contact(series[A.WRIST_ELEVATION_PX])
        a, b = moment(seq, clip.hand, contact, which, clip.trophy)
        bt = body_angle(seq, clip.hand, slice(a, b))
        cat = real_category(clip.view)
        side = LABELS[clip.id].get("side")
        truth = true_angle(cat, side)
        out.append({"clip": clip.id, "player": clip.player, "true": cat, "true_side": side, "truth": truth,
                    "body": bt.angle_deg, "implied_turn": None if bt.angle_deg is None else wrap(bt.angle_deg - truth)})
    return out


def circular_median(values: list[float]) -> float:
    vals = np.array(values)
    grid = np.arange(-180, 180, 1.0)
    cost = [np.abs(((vals - g + 180) % 360) - 180).sum() for g in grid]
    return float(grid[int(np.argmin(cost))])


def real(which: str, fixed_turn: float | None) -> tuple[list[dict], dict[str, float]]:
    clips = real_turns(which)
    rows, fitted = [], {}
    for c in clips:
        if fixed_turn is None:  # fit on every other player
            others = [o["implied_turn"] for o in clips if o["player"] != c["player"] and o["implied_turn"] is not None]
            turn = circular_median(others)
        else:
            turn = fixed_turn
        fitted[c["player"]] = turn
        if c["body"] is None:
            pred, side = "none", None
        else:
            pred, side, _ = categorise((c["body"] - turn) % 360)
        rows.append({**c, "pred": pred, "pred_side": side, "turn": turn})
    return rows, fitted


# --- 3. reliability -----------------------------------------------------------------------------------

def reliability(stance_turns: tuple[float, ...]) -> tuple[dict[str, dict[str, float]], list[str]]:
    """{view: {"phase.metric": 90th-percentile error}} on the rig, across stances and knee directions.
    The knees turn with the stance (the rig's knee directions are for its 80° stance)."""
    errs: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for cam in sy.CAMERAS:
        for base in sy.SERVE_SPECS:
            for st in stance_turns:
                spec = replace(base, stance_turn_deg=st, knee_dir_deg=base.knee_dir_deg + (st - 80.0))
                serve = sy.make_serve(spec)
                truth = sy.true_series(serve)
                series = A.compute_series(sy.film(serve, cam), spec.hand)
                _, cat, side = rig_truth(cam, spec.hand)
                view = cam.group if cam.group == "high" else (f"{cat} ({side})" if side else cat)
                if cam.group == "high":
                    view = cam.name
                for phase, metrics in PHASE_METRICS.items():
                    frame = getattr(serve.phases, phase)
                    for m in metrics:
                        v = series[m][frame]
                        err = abs(v - truth[m][frame]) if np.isfinite(v) else np.inf
                        errs[view][f"{phase}.{m}"].append(err)
    table = {view: {k: float(np.percentile(v, 90)) for k, v in by.items()} for view, by in errs.items()}
    keys = [f"{p}.{m}" for p, ms in PHASE_METRICS.items() for m in ms]
    return table, keys


def limit(key: str) -> float:
    return 0.1 if key.endswith("wrist_height") else 10.0


# --- report ---------------------------------------------------------------------------------------------

def main() -> None:
    REPORTS.mkdir(exist_ok=True)
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    lines = [f"# View detection: {stamp} ({commit}{'-dirty' if dirty else ''})", ""]

    lines += ["## 1. Synthetic rig", "",
              "Each variant takes the body's turn at one moment and subtracts a fixed stance turn "
              f"({STANCE_TURN_DEG:.0f}°, the rig's own).", ""]
    for label, turns in (("stance fixed at 80° (the rig's default)", (80.0,)),
                         (f"stance varied like real players ({', '.join(f'{t:.0f}°' for t in REAL_STANCE_TURNS)})",
                          REAL_STANCE_TURNS)):
        rows, errors, ms = synthetic(turns, "set", STANCE_TURN_DEG)
        lines += [f"### Set position, {label}", "",
                  f"{len(rows)} clips · median angle error **{np.median(errors):.1f}°**, 90th percentile "
                  f"{np.percentile(errors, 90):.1f}° · {ms:.2f} ms per clip", "", targets_line(score(rows)), "",
                  confusion(rows), ""]

    lines += ["## 2. Real labelled clips", "",
              "The stance turn is fitted leaving each player out (circular median of the turn each other clip's "
              "label implies), except the first row, which uses the rig's 80°.", "",
              "| Moment | Stance turn | Side-on detection | Side | Category |", "|---|---|---|---|---|"]
    detail = {}
    for which, fixed in (("set", STANCE_TURN_DEG), ("set", None), ("trophy", None), ("contact", None)):
        rows, fitted = real(which, fixed)
        s = score(rows)
        turn = f"{fixed:.0f}° (fixed)" if fixed is not None else "fitted, leave-one-player-out"
        lines.append(f"| {which} | {turn} | {s['side-on detection']:.0%} | {s['side']:.0%} | {s['category']:.0%} |")
        detail[(which, fixed)] = rows
    lines += ["", f"Targets: side-on detection {TARGETS['side-on detection']:.0%}, side {TARGETS['side']:.0%}, "
              f"category {TARGETS['category']:.0%}.", ""]

    rows = detail[("set", STANCE_TURN_DEG)]
    lines += ["### The stance turn each clip implies", "",
              "Body angle at the set position minus the camera angle its label implies: how far that player was "
              "turned from the net, if the label is right. The rig assumes 80° for everyone.", "",
              "| Clip | Player | Label | Side | Body angle | Implied turn | Predicted (80°) |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        body = "—" if r["body"] is None else f"{r['body']:.0f}°"
        turn = "—" if r["implied_turn"] is None else f"{r['implied_turn']:+.0f}°"
        pred = r["pred"] + (f" ({r['pred_side']})" if r["pred_side"] else "")
        lines.append(f"| {r['clip']} | {r['player']} | {r['true']} | {r['true_side'] or '—'} | {body} | {turn} | {pred} |")
    by_player = defaultdict(list)
    for r in rows:
        if r["implied_turn"] is not None:
            by_player[r["player"]].append(r["implied_turn"])
    lines += ["", "Implied stance turn by player: " + "; ".join(
        f"{p} {min(v):+.0f}° to {max(v):+.0f}°" for p, v in by_player.items()) + ".", ""]
    lines += ["### Confusion matrix, set position, fitted turn", "", confusion(detail[("set", None)]), ""]

    lines += ["## 3. Which measurements each view supports (rig)", "",
              "90th-percentile error of the 2D measurement at the true phase frame, against the exact 3D value. "
              "✓ = within 10° (0.1 body heights for wrist height). The knees turn with the stance.", ""]
    for label, turns in (("Stance fixed at 80° (the rig's default)", (80.0,)),
                         ("Stance varied like real players", REAL_STANCE_TURNS)):
        table, keys = reliability(turns)
        lines += [f"### {label}", "",
                  "| View | " + " | ".join(k.replace("_", " ") for k in keys) + " |", "|---|" + "---|" * len(keys)]
        for view in sorted(table, key=lambda v: (v.startswith("side-on,") or v.startswith("behind,"), v)):
            cells = []
            for k in keys:
                e = table[view][k]
                cells.append(("✓ " if e <= limit(k) else "✗ ")
                             + ("∞" if not np.isfinite(e) else (f"{e:.2f}" if k.endswith("height") else f"{e:.0f}°")))
            lines.append(f"| {view} | " + " | ".join(cells) + " |")
        lines.append("")

    out = REPORTS / f"views_{stamp}_{commit}{'-dirty' if dirty else ''}.md"
    out.write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"\nwrote {out}")


TABLE = Path(__file__).resolve().parents[1] / "serve_analyzer" / "data" / "view_reliability.json"
# Rig view names -> the camera positions people choose at upload (serve_analyzer.view.CAMERA_VIEWS).
RIG_TO_CAMERA_VIEW = {
    "behind": "behind", "behind-diagonal (hitting)": "behind_diagonal_hitting",
    "behind-diagonal (toss)": "behind_diagonal_toss", "side-on (hitting)": "side_hitting",
    "side-on (toss)": "side_toss", "front-diagonal (hitting)": "front_diagonal_hitting",
    "front-diagonal (toss)": "front_diagonal_toss", "front": "front",
}


def write_table() -> None:
    """The rig's per-view errors at the rig's own 80° stance, for the pipeline to label
    measurements with when someone says where their camera was."""
    table, keys = reliability((80.0,))
    out = {"_note": ("90th-percentile error of each 2D measurement against the exact 3D value, by camera "
                     "position, on the synthetic rig (degrees; body heights for wrist_height). Generated by "
                     "`python -m evaluation.views table`; see docs/view-detection.md."),
           "views": {RIG_TO_CAMERA_VIEW[v]: {k: round(e, 1 if not k.endswith("height") else 3) for k, e in table[v].items()}
                     for v in RIG_TO_CAMERA_VIEW}}
    TABLE.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {TABLE}")


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["table"]:
        write_table()
    else:
        main()

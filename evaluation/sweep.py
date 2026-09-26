"""One-factor-at-a-time parameter sweeps over the synthetic benchmark and real clips.

    python -m evaluation.sweep            # full sweep, writes evaluation/reports/<time>_<commit>.{md,json}
    python -m evaluation.sweep --quick    # baseline only

Every experiment changes exactly one setting from the baseline, so any change in
the scores is caused by that setting. The combined configuration is then checked
as a whole to catch interactions.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from pathlib import Path

import numpy as np

from serve_analyzer import feedback
from serve_analyzer.config import AnalysisConfig
from serve_analyzer.metrics import compute_metrics
from serve_analyzer.models import PhaseFrames
from serve_analyzer.pipeline import measure
from serve_analyzer.reference import Range, RangeTable, assess, load_ranges

from . import real, synthetic

REPORTS = Path(__file__).parent / "reports"
PHASES = ("trophy", "racket_drop", "contact")
CHECKS = [
    ("front_knee_flexion", "trophy"), ("back_knee_flexion", "trophy"), ("elbow_angle", "trophy"),
    ("trunk_tilt", "trophy"), ("elbow_angle", "racket_drop"), ("elbow_angle", "contact"), ("wrist_height", "contact"),
]
SHORT = {"front_knee_flexion": "F-knee", "back_knee_flexion": "B-knee", "elbow_angle": "elbow",
         "trunk_tilt": "trunk", "wrist_height": "wrist-h"}


@dataclass(frozen=True)
class Variant:
    name: str
    config: AnalysisConfig = field(default_factory=AnalysisConfig)
    borderline_scale: float = 1.0
    max_points: int = feedback.MAX_POINTS


def scaled_ranges(ranges: RangeTable, scale: float) -> RangeTable:
    """Widen or narrow each borderline band around its (unchanged) good range."""
    out: RangeTable = {}
    for phase, by in ranges.items():
        out[phase] = {}
        for metric, r in by.items():
            (glo, ghi), (blo, bhi) = r.good, r.borderline
            out[phase][metric] = Range(r.good, (glo - scale * (glo - blo), ghi + scale * (bhi - ghi)))
    return out


def run(seq, hand, cfg: AnalysisConfig):
    _, series, phases = measure(seq, hand, cfg)
    return series, phases, compute_metrics(series, phases)


def _labels(metrics, ranges) -> dict:
    return {(a.phase, a.metric): a.status for a in assess(metrics, ranges)}


def _feedback_keys(metrics, ranges, max_points) -> set:
    return {(f.phase, f.metric) for f in feedback.generate(assess(metrics, ranges), max_points) if f.phase}


def _truth_metrics(truth: dict, phases: PhaseFrames) -> dict:
    return {p: {m: float(truth[m][getattr(phases, p)]) for m in truth} for p in PHASES}


def evaluate_synthetic(v: Variant, base_ranges: RangeTable) -> dict:
    ranges = scaled_ranges(base_ranges, v.borderline_scale)
    phase_err = {p: [] for p in PHASES}
    phase_miss = {p: 0 for p in PHASES}
    metric_err = {c: [] for c in CHECKS}
    label_hits = label_total = 0
    jaccards = []
    by_group: dict[str, dict] = {}
    spreads = {c: [] for c in CHECKS}
    runs = 0
    for spec in synthetic.SERVE_SPECS:
        serve = synthetic.make_serve(spec)
        truth = synthetic.true_series(serve)
        truth_metrics = _truth_metrics(truth, serve.phases)
        truth_labels = _labels(truth_metrics, ranges)
        truth_fb = _feedback_keys(truth_metrics, ranges, v.max_points)
        per_view_values = {c: [] for c in CHECKS}
        for cam in synthetic.CAMERAS:
            seq = synthetic.film(serve, cam)
            series, phases, metrics = run(seq, spec.hand, v.config)
            runs += 1
            g = by_group.setdefault(cam.group, {"metric_err": [], "phase_err": [], "label_hits": 0, "label_total": 0})
            for p in PHASES:
                det, true = getattr(phases, p), getattr(serve.phases, p)
                if det is None:
                    phase_miss[p] += 1
                else:
                    phase_err[p].append(abs(det - true))
                    g["phase_err"].append(abs(det - true))
            for c in CHECKS:
                m, p = c
                est = float(series[m][getattr(serve.phases, p)])
                err = abs(est - truth[m][getattr(serve.phases, p)])
                if m == "wrist_height":
                    err *= 100  # report wrist height error in hundredths of body height
                metric_err[c].append(err)
                if m != "wrist_height":
                    g["metric_err"].append(err)
                val = metrics[p][m]
                per_view_values[c].append(np.nan if val is None else val)
            est_labels = _labels(metrics, ranges)
            for key, truth_status in truth_labels.items():
                label_total += 1
                g["label_total"] += 1
                if est_labels.get(key) == truth_status:
                    label_hits += 1
                    g["label_hits"] += 1
            est_fb = _feedback_keys(metrics, ranges, v.max_points)
            union = truth_fb | est_fb
            jaccards.append(len(truth_fb & est_fb) / len(union) if union else 1.0)
        for c in CHECKS:
            vals = np.array(per_view_values[c], float)
            if np.sum(~np.isnan(vals)) >= 2:
                spreads[c].append(float(np.nanstd(vals)) * (100 if c[0] == "wrist_height" else 1))

    def mae(xs):
        xs = np.array(xs, float)
        return float(np.nanmean(xs)) if np.any(~np.isnan(xs)) else float("nan")

    angle_checks = [c for c in CHECKS if c[0] != "wrist_height"]
    return {
        "runs": runs,
        "phase_mae": {p: mae(phase_err[p]) for p in PHASES},
        "phase_miss_rate": {p: phase_miss[p] / runs for p in PHASES},
        "metric_mae": {f"{SHORT[m]}@{p}": mae(metric_err[(m, p)]) for m, p in CHECKS},
        "metric_coverage": {f"{SHORT[m]}@{p}": float(np.mean(~np.isnan(metric_err[(m, p)]))) for m, p in CHECKS},
        "angle_mae": mae([e for c in angle_checks for e in metric_err[c]]),
        "view_spread": {f"{SHORT[m]}@{p}": mae(spreads[(m, p)]) for m, p in CHECKS},
        "angle_view_spread": mae([s for c in angle_checks for s in spreads[c]]),
        "label_accuracy": label_hits / label_total,
        "feedback_jaccard": float(np.mean(jaccards)),
        "by_group": {
            k: {"angle_mae": mae(g["metric_err"]), "phase_mae": mae(g["phase_err"]),
                "label_accuracy": g["label_hits"] / g["label_total"]}
            for k, g in by_group.items()
        },
    }


def evaluate_real(v: Variant) -> dict:
    trophy_err, contact_err, misses, phantom_rejected, real_serve_lost = [], [], 0, None, 0
    per_clip = {}
    values: dict[str, dict[str, list]] = {}
    for clip in real.load_clips():
        seq = real.load_pose(clip)
        _, phases, metrics = run(seq, clip.hand, v.config)
        per_clip[clip.id] = phases.as_dict()
        if clip.contact is None:
            phantom_rejected = phases.contact is None
            continue
        if phases.contact is None:
            real_serve_lost += 1
        else:
            contact_err.append(abs(phases.contact - clip.contact))
        if clip.trophy is not None:
            if phases.trophy is None:
                misses += 1
            else:
                trophy_err.append(abs(phases.trophy - clip.trophy))
        for m, p in CHECKS:
            values.setdefault(clip.player, {}).setdefault(f"{SHORT[m]}@{p}", []).append(metrics[p][m])
    spread = {}
    for player, by in values.items():
        spread[player] = {}
        for k, vals in by.items():
            arr = np.array([np.nan if x is None else x for x in vals], float)
            spread[player][k] = float(np.nanmax(arr) - np.nanmin(arr)) if np.sum(~np.isnan(arr)) >= 2 else float("nan")
    return {
        "trophy_mae": float(np.mean(trophy_err)) if trophy_err else float("nan"),
        "trophy_within_2": float(np.mean([e <= 2 for e in trophy_err] + [False] * misses)),
        "trophy_missed": misses,
        "contact_mae": float(np.mean(contact_err)) if contact_err else float("nan"),
        "contact_within_1": float(np.mean([e <= 1 for e in contact_err] + [False] * real_serve_lost)),
        "real_serves_lost": real_serve_lost,
        "phantom_rejected": phantom_rejected,
        "metric_spread": spread,
        "phases": per_clip,
    }


def experiments(base: AnalysisConfig) -> list[tuple[str, list[Variant]]]:
    def cfg(**kw) -> AnalysisConfig:
        return replace(base, **kw)

    smoothing = [Variant("off", cfg(smoothing_enabled=False))] + [
        Variant(f"{w} ms", cfg(smoothing_window_ms=w)) for w in (50, 100, 150, 250, 400)
    ]
    return [
        ("Smoothing window", smoothing),
        ("Smoothing polynomial order", [Variant(f"order {o}", cfg(smoothing_polyorder=o)) for o in (2, 3)]),
        ("Visibility threshold", [Variant(f"{t}", cfg(visibility_threshold=t)) for t in (0.0, 0.1, 0.3, 0.5, 0.7)]),
        ("Max gap filled", [Variant(f"{g} frames", cfg(max_gap_frames=g)) for g in (0, 5, 10, 20)]),
        ("Angle space", [Variant(s, cfg(angle_space=s)) for s in ("image2d", "world3d")]),
        ("Angle space x visibility threshold (interaction)",
         [Variant(f"world3d, vis {t}", cfg(angle_space="world3d", visibility_threshold=t)) for t in (0.0, 0.1, 0.3, 0.5)]),
        ("Phase timing signals (with 3D angles)",
         [Variant(f"world3d angles, phases from {s}", cfg(angle_space="world3d", phase_signal_space=s)) for s in ("angle_space", "image2d")]),
        ("Contact visibility threshold (angles stay at 0.5)",
         [Variant(f"{t}", cfg(contact_visibility_threshold=t)) for t in (None, 0.0, 0.1, 0.3)]),
        ("Trophy rule", [Variant(m, cfg(trophy_method=m)) for m in ("knee_toss", "toss_peak")]),
        ("Trophy search window before contact", [Variant(f"{w} s" if w else "none", cfg(trophy_window_s=w)) for w in (None, 1.2, 1.0, 0.8, 0.6)]),
        ("Trophy fallback when knees are unmeasurable", [Variant(str(b), cfg(trophy_fallback=b)) for b in (False, True)]),
        ("Trophy plateau centre (deg below peak)", [Variant(f"{d}" if d else "argmax", cfg(trophy_plateau_deg=d)) for d in (None, 2.0, 4.0, 6.0)]),
        ("Racket-drop rule", [Variant(m, cfg(racket_drop_method=m)) for m in ("min_elbow", "wrist_low")]),
        ("Complete-serve check", [Variant(str(b), cfg(require_complete_serve=b)) for b in (False, True)]),
        ("Borderline band width (x current)", [Variant(f"x{s}", base, borderline_scale=s) for s in (0.5, 1.0, 1.5, 2.0)]),
        ("Feedback points shown", [Variant(f"{k}", base, max_points=k) for k in (2, 3, 4, 5)]),
    ]


def candidates(base: AnalysisConfig) -> list[Variant]:
    """Combinations of the one-at-a-time winners, to check they still help together."""
    best = replace(base, angle_space="world3d", phase_signal_space="image2d", contact_visibility_threshold=0.1,
                   trophy_window_s=0.8, trophy_fallback=True, require_complete_serve=True)
    return [
        Variant("NEW DEFAULTS (phase changes, 2D angles)", AnalysisConfig()),
        Variant("new defaults + world3d angles", replace(AnalysisConfig(), angle_space="world3d")),
        Variant("combined: all winners", best),
        Variant("combined, no trophy fallback", replace(best, trophy_fallback=False)),
        Variant("combined, no complete-serve check", replace(best, require_complete_serve=False)),
        Variant("combined, smoothing off", replace(best, smoothing_enabled=False)),
        Variant("combined, 2D angles (phase changes only)", replace(best, angle_space="image2d")),
    ]


def commit_id() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def evaluate(v: Variant, ranges: RangeTable) -> dict:
    t0 = time.time()
    out = {"variant": v.name, "config": {k: (str(x) if isinstance(x, Path) else x) for k, x in asdict(v.config).items()},
           "borderline_scale": v.borderline_scale, "max_points": v.max_points,
           "synthetic": evaluate_synthetic(v, ranges), "real": evaluate_real(v)}
    out["seconds"] = time.time() - t0
    return out


def fmt(x, digits=1):
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{digits}f}"


def row(r: dict) -> str:
    s, re_ = r["synthetic"], r["real"]
    return (f"| {r['variant']} | {fmt(s['angle_mae'])} | {fmt(s['angle_view_spread'])} | "
            f"{fmt(s['phase_mae']['trophy'])} / {fmt(100 * s['phase_miss_rate']['trophy'], 0)}% | "
            f"{fmt(s['phase_mae']['racket_drop'])} | {fmt(s['phase_mae']['contact'])} | "
            f"{fmt(100 * s['label_accuracy'], 0)}% | {fmt(s['feedback_jaccard'], 2)} | "
            f"{fmt(re_['trophy_mae'])} ({re_['trophy_missed']} missed) | {fmt(re_['contact_mae'])} | "
            f"{'yes' if re_['phantom_rejected'] else 'no'} |")


HEADER = ("| Setting | Angle MAE ° | View spread ° | Trophy err / miss (syn) | Drop err (syn) | Contact err (syn) "
          "| Label acc | Feedback overlap | Trophy err (real) | Contact err (real) | Phantom rejected |\n"
          "|---|---|---|---|---|---|---|---|---|---|---|")


def write_report(baseline: dict, groups: list[tuple[str, list[dict]]], combined: list[dict], stamp: str) -> Path:
    lines = [f"# Parameter sweep — {stamp}", "",
             "Synthetic: 12 exact serves × 10 virtual cameras with a detector-noise model. Metric errors are",
             "measured at the true phase frames; view spread = std of the same serve's metric across cameras,",
             "at detected phases. Real: 11 labelled clips, phase errors in frames. Wrist height is excluded from",
             "the angle averages. Lower is better except label accuracy, feedback overlap and phantom rejection.",
             "", "## Baseline", "", HEADER, row(baseline), ""]
    for title, results in groups:
        lines += [f"## {title}", "", HEADER] + [row(r) for r in results] + [""]
    lines += ["## Combined", "", HEADER] + [row(r) for r in combined] + [""]
    for r in [baseline] + combined:
        s = r["synthetic"]
        lines += [f"### Per-metric detail: {r['variant']}", "",
                  "| Check | MAE | Coverage | View spread |", "|---|---|---|---|"]
        for k in s["metric_mae"]:
            unit = " (×100 body height)" if k.startswith("wrist") else " °"
            lines.append(f"| {k}{unit} | {fmt(s['metric_mae'][k])} | {fmt(100 * s['metric_coverage'][k], 0)}% | {fmt(s['view_spread'][k])} |")
        lines += ["", "| Camera group | Angle MAE ° | Phase err (frames) | Label acc |", "|---|---|---|---|"]
        for g, gv in sorted(s["by_group"].items()):
            lines.append(f"| {g} | {fmt(gv['angle_mae'])} | {fmt(gv['phase_mae'])} | {fmt(100 * gv['label_accuracy'], 0)}% |")
        lines.append("")
    REPORTS.mkdir(exist_ok=True)
    path = REPORTS / f"{stamp}.md"
    path.write_text("\n".join(lines) + "\n")
    path.with_suffix(".json").write_text(json.dumps(
        {"baseline": baseline, "groups": [{"title": t, "results": rs} for t, rs in groups], "combined": combined},
        indent=1, default=float))
    return path


# The pipeline as it was before tuning; every report compares against this.
ORIGINAL_DEFAULTS = AnalysisConfig(require_complete_serve=False, contact_visibility_threshold=None, trophy_window_s=None)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    ranges = load_ranges()
    base = ORIGINAL_DEFAULTS
    stamp = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{commit_id()}"
    baseline = evaluate(Variant("original defaults (before tuning)", base), ranges)
    print(HEADER.splitlines()[0]); print(row(baseline), flush=True)
    groups = []
    if not args.quick:
        for title, variants in experiments(base):
            results = [evaluate(v, ranges) for v in variants]
            groups.append((title, results))
            print(f"\n{title}")
            for r in results:
                print(row(r), flush=True)
    combined = [evaluate(v, ranges) for v in candidates(base)]
    print("\nCombined")
    for r in combined:
        print(row(r), flush=True)
    path = write_report(baseline, groups, combined, stamp)
    print(f"\nreport: {path}")


if __name__ == "__main__":
    main()

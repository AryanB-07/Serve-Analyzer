"""How well does MediaPipe capture depth? Ground-truth-free tests on real clips.

    python -m evaluation.depth

1. Depth scale from bone-length constancy. Bones don't change length. If MediaPipe
   reports depth as s x true depth, a bone pointing at the camera looks shorter than
   the same bone lying across the image. For each bone we find the s that makes its
   3D length most constant over the clip: s = 1 means depth is captured at the right
   scale, s < 1 means it is compressed. The estimator is checked first on synthetic
   data with a known s.
2. Mirror consistency. Run MediaPipe on horizontally flipped video: a consistent model
   returns mirrored x and identical y and depth. Disagreement shows how much of each
   axis is inferred rather than observed.
3. Distance sensitivity. Downscale frames 2x and 4x (a player 2x/4x further away) and
   compare with full resolution.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from serve_analyzer.angles import joint_angle
from serve_analyzer.config import AnalysisConfig
from serve_analyzer.models import Hand, PoseSequence
from serve_analyzer.pose import ensure_model, extract_pose_sequence
from serve_analyzer.video import probe

from . import real, synthetic
from .sweep import commit_id

REPORTS = Path(__file__).parent / "reports"
BONES = {
    "L thigh": (23, 25), "R thigh": (24, 26), "L shin": (25, 27), "R shin": (26, 28),
    "L upper arm": (11, 13), "R upper arm": (12, 14), "L forearm": (13, 15), "R forearm": (14, 16),
}
BODY = [0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]
MIRROR = {11: 12, 12: 11, 13: 14, 14: 13, 15: 16, 16: 15, 23: 24, 24: 23, 25: 26, 26: 25, 27: 28, 28: 27, 0: 0}
SCALES = np.round(np.arange(0.1, 2.51, 0.02), 2)


# --- 1. depth scale ---------------------------------------------------------------------------

def bone_depth_scale(world: np.ndarray, vis: np.ndarray, a: int, b: int, min_vis: float = 0.5,
                     min_frames: int = 20, min_depth_spread: float = 0.12) -> tuple[float, int, float]:
    """(s, frames used, std of the bone's depth fraction). s is NaN when unidentifiable:
    too few confident frames, or the bone never changes how much it points at the camera."""
    ok = (vis[:, a] >= min_vis) & (vis[:, b] >= min_vis) & ~np.isnan(world[:, a, 0]) & ~np.isnan(world[:, b, 0])
    v = world[ok, b] - world[ok, a]
    if len(v) < min_frames:
        return float("nan"), len(v), float("nan")
    frac = np.abs(v[:, 2]) / np.linalg.norm(v, axis=1)
    spread = float(np.std(frac))
    if spread < min_depth_spread:
        return float("nan"), len(v), spread
    cvs = []
    for s in SCALES:
        length = np.sqrt(v[:, 0] ** 2 + v[:, 1] ** 2 + (v[:, 2] / s) ** 2)
        cvs.append(np.std(length) / np.mean(length))
    return float(SCALES[int(np.argmin(cvs))]), len(v), spread


def clip_depth_scales(seq: PoseSequence) -> dict[str, float]:
    return {name: bone_depth_scale(seq.world, seq.landmarks[..., 2], a, b)[0] for name, (a, b) in BONES.items()}


def validate_estimator() -> list[tuple[float, float, int]]:
    """Recover a known depth scale from synthetic serves: (true s, median estimate, bones used)."""
    out = []
    for true_s in (0.3, 0.5, 0.75, 1.0, 1.5):
        noise = replace(synthetic.NoiseModel(), depth_scale_range=(true_s, true_s))
        estimates = []
        for spec in synthetic.SERVE_SPECS[:6]:
            serve = synthetic.make_serve(spec)
            for cam in synthetic.CAMERAS[:8]:
                estimates += [s for s in clip_depth_scales(synthetic.film(serve, cam, noise)).values() if not np.isnan(s)]
        out.append((true_s, float(np.median(estimates)), len(estimates)))
    return out


# --- variants of the real clips (flipped, downscaled) -------------------------------------------

def load_variant(clip: real.Clip, name: str, transform: Callable[[np.ndarray], np.ndarray]) -> PoseSequence:
    path = real.CACHE / "landmarks" / f"{clip.id}.heavy-{name}.npz"
    if not path.exists():
        cfg = AnalysisConfig()
        seq = extract_pose_sequence(probe(clip.path), ensure_model("heavy", cfg.model_dir), transform)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, landmarks=seq.landmarks, world=seq.world, fps=seq.fps, width=seq.width, height=seq.height)
    d = np.load(path)
    return PoseSequence(d["landmarks"], float(d["fps"]), int(d["width"]), int(d["height"]), world=d["world"])


def mirror_disagreement(orig: PoseSequence, flipped: PoseSequence) -> dict[str, float]:
    """Mean |difference| per axis (cm) between a clip and its mirrored re-run, confident joints only,
    plus each axis's spread (std across body joints) for scale."""
    diffs, spreads = {"x": [], "y": [], "z": []}, {"x": [], "y": [], "z": []}
    n = min(orig.n_frames, flipped.n_frames)
    for j in BODY:
        m = MIRROR[j]
        ok = (orig.landmarks[:n, j, 2] >= 0.5) & (flipped.landmarks[:n, m, 2] >= 0.5)
        a, b = orig.world[:n][ok, j], flipped.world[:n][ok, m]
        b = b * np.array([-1.0, 1.0, 1.0])
        for k, axis in enumerate("xyz"):
            diffs[axis] += list(np.abs(a[:, k] - b[:, k]))
    for k, axis in enumerate("xyz"):
        spreads[axis] = float(np.nanmean(np.nanstd(orig.world[:, BODY, k], axis=1)))
    return {**{f"d{a}": 100 * float(np.nanmean(diffs[a])) for a in "xyz"},
            **{f"spread_{a}": 100 * spreads[a] for a in "xyz"}}


def mirror_angle_disagreement(orig: PoseSequence, flipped: PoseSequence, hand: Hand) -> dict[str, float]:
    """Median |angle change| when the same clip is mirrored, in 2D and in 3D.

    Flipping is exact geometry, so a perfectly consistent model gives identical angles
    (the mirrored player is measured with the other hand). 2D shows the detector's own
    noise; 3D adds whatever the depth estimate changes.
    """
    n = min(orig.n_frames, flipped.n_frames)
    out = {}
    for name, (joints, joints_m) in {
        "knee": (((23, 25, 27), (24, 26, 28)) if hand is Hand.RIGHT else ((24, 26, 28), (23, 25, 27))),
        "elbow": (((12, 14, 16), (11, 13, 15)) if hand is Hand.RIGHT else ((11, 13, 15), (12, 14, 16))),
    }.items():
        ok = np.all(orig.landmarks[:n, list(joints), 2] >= 0.5, axis=1) & np.all(flipped.landmarks[:n, list(joints_m), 2] >= 0.5, axis=1)
        for space, a, b in (("2d", orig.landmarks[:n, :, :2], flipped.landmarks[:n, :, :2]), ("3d", orig.world[:n], flipped.world[:n])):
            ang_a = joint_angle(a[:, joints[0]], a[:, joints[1]], a[:, joints[2]])
            ang_b = joint_angle(b[:, joints_m[0]], b[:, joints_m[1]], b[:, joints_m[2]])
            d = np.abs(ang_a - ang_b)[ok]
            out[f"{name}_{space}"] = float(np.nanmedian(d)) if d.size else float("nan")
    return out


def angle_series(seq: PoseSequence, hand: Hand) -> dict[str, np.ndarray]:
    w = seq.world
    hs, he, hw = (12, 14, 16) if hand is Hand.RIGHT else (11, 13, 15)
    return {
        "front knee": 180 - joint_angle(w[:, 23], w[:, 25], w[:, 27]) if hand is Hand.RIGHT
        else 180 - joint_angle(w[:, 24], w[:, 26], w[:, 28]),
        "elbow": joint_angle(w[:, hs], w[:, he], w[:, hw]),
    }


def main() -> None:
    stamp = f"depth_{datetime.now().strftime('%Y%m%d-%H%M%S')}_{commit_id()}"
    lines = [f"# MediaPipe depth study — {stamp}", ""]

    print("1a. Estimator check on synthetic data (known depth scale)")
    lines += ["## 1a. Estimator check (synthetic, known depth scale)", "", "| True s | Estimated s (median) | Bones |", "|---|---|---|"]
    for true_s, est, n in validate_estimator():
        print(f"  true {true_s:4.2f} -> estimated {est:4.2f}  ({n} bones)")
        lines.append(f"| {true_s:.2f} | {est:.2f} | {n} |")

    clips = [c for c in real.load_clips()]
    print("\n1b. Depth scale on real clips, per bone (NaN = bone never swings through depth enough to tell)")
    lines += ["", "## 1b. Depth scale on real MediaPipe output", "",
              "| Clip | View | " + " | ".join(BONES) + " | Median |", "|---|---|" + "---|" * (len(BONES) + 1)]
    by_view: dict[str, list[float]] = {}
    for c in clips:
        scales = clip_depth_scales(real.load_pose(c))
        vals = [v for v in scales.values() if not np.isnan(v)]
        med = float(np.median(vals)) if vals else float("nan")
        by_view.setdefault(c.view, []).extend(vals)
        cells = " | ".join("—" if np.isnan(v) else f"{v:.2f}" for v in scales.values())
        print(f"  {c.id:14s} {c.view:16s} median s = {med:.2f}  ({len(vals)} bones)")
        lines.append(f"| {c.id} | {c.view} | {cells} | {med:.2f} |")
    lines += ["", "| View | Median s | IQR | Bones |", "|---|---|---|---|"]
    print("  by view:")
    for view, vals in by_view.items():
        if vals:
            q1, q2, q3 = np.percentile(vals, [25, 50, 75])
            print(f"    {view:16s} median {q2:.2f}  IQR {q1:.2f}-{q3:.2f}  ({len(vals)} bones)")
            lines.append(f"| {view} | {q2:.2f} | {q1:.2f}–{q3:.2f} | {len(vals)} |")
    all_vals = [v for vals in by_view.values() for v in vals]
    q1, q2, q3 = np.percentile(all_vals, [25, 50, 75])
    print(f"    ALL              median {q2:.2f}  IQR {q1:.2f}-{q3:.2f}  ({len(all_vals)} bones)")
    lines.append(f"| **all** | **{q2:.2f}** | {q1:.2f}–{q3:.2f} | {len(all_vals)} |")

    print("\n2. Mirror consistency (flipped video; cm, confident joints)")
    lines += ["", "## 2. Mirror consistency (flipped video)", "",
              "Mean |difference| between a clip's world landmarks and its mirrored re-run, in cm, next to each axis's "
              "spread across the body. A depth estimate that is as consistent as x and y has a similar ratio.", "",
              "| Clip | View | Δx | Δy | Δdepth | Δ/spread x | Δ/spread y | Δ/spread depth |", "|---|---|---|---|---|---|---|---|"]
    ratios = {"x": [], "y": [], "z": []}
    for c in clips:
        r = mirror_disagreement(real.load_pose(c), load_variant(c, "flip", lambda f: cv2.flip(f, 1)))
        rel = {a: r[f"d{a}"] / r[f"spread_{a}"] for a in "xyz"}
        for a in "xyz":
            ratios[a].append(rel[a])
        print(f"  {c.id:14s} {c.view:16s} Δx {r['dx']:4.1f} Δy {r['dy']:4.1f} Δz {r['dz']:4.1f} cm | relative {rel['x']:.2f} {rel['y']:.2f} {rel['z']:.2f}")
        lines.append(f"| {c.id} | {c.view} | {r['dx']:.1f} | {r['dy']:.1f} | {r['dz']:.1f} | {rel['x']:.2f} | {rel['y']:.2f} | {rel['z']:.2f} |")
    med = {a: float(np.median(ratios[a])) for a in "xyz"}
    print(f"  median relative disagreement: x {med['x']:.2f}  y {med['y']:.2f}  depth {med['z']:.2f}")
    lines.append(f"| **median** | | | | | **{med['x']:.2f}** | **{med['y']:.2f}** | **{med['z']:.2f}** |")

    print("\n2b. What mirroring does to the angles (median |change|, degrees)")
    lines += ["", "### 2b. Angle change under mirroring (median, degrees)", "",
              "| Clip | View | Knee 2D | Knee 3D | Elbow 2D | Elbow 3D |", "|---|---|---|---|---|---|"]
    by_view_ang: dict[str, list[dict]] = {}
    for c in clips:
        r = mirror_angle_disagreement(real.load_pose(c), load_variant(c, "flip", lambda f: cv2.flip(f, 1)), c.hand)
        by_view_ang.setdefault(c.view, []).append(r)
        f = lambda x: "—" if np.isnan(x) else f"{x:.1f}"  # noqa: E731
        print(f"  {c.id:14s} {c.view:16s} knee 2D {f(r['knee_2d']):>5s} 3D {f(r['knee_3d']):>5s} | elbow 2D {f(r['elbow_2d']):>5s} 3D {f(r['elbow_3d']):>5s}")
        lines.append(f"| {c.id} | {c.view} | {f(r['knee_2d'])} | {f(r['knee_3d'])} | {f(r['elbow_2d'])} | {f(r['elbow_3d'])} |")
    lines += ["", "| View | Knee 2D | Knee 3D | Elbow 2D | Elbow 3D |", "|---|---|---|---|---|"]
    print("  by view (median of clip medians):")
    for view, rs in by_view_ang.items():
        m = {k: float(np.nanmedian([r[k] for r in rs])) for k in rs[0]}
        print(f"    {view:28s} knee {m['knee_2d']:4.1f} -> {m['knee_3d']:4.1f}   elbow {m['elbow_2d']:4.1f} -> {m['elbow_3d']:4.1f}")
        lines.append(f"| {view} | {m['knee_2d']:.1f} | {m['knee_3d']:.1f} | {m['elbow_2d']:.1f} | {m['elbow_3d']:.1f} |")

    print("\n3. Distance sensitivity (downscaled frames vs full resolution)")
    lines += ["", "## 3. Distance sensitivity (downscaled frames)", "",
              "| Clip | Scale | Person height px | Frames detected | Mean vis. | Δ world x/y/depth (cm) | Knee Δ° | Elbow Δ° |",
              "|---|---|---|---|---|---|---|---|"]
    for cid in ("pex_side", "pex_behind", "pex_frontdiag", "pex_front_far"):
        c = next(x for x in clips if x.id == cid)
        full = real.load_pose(c)
        fa = angle_series(full, c.hand)
        for scale in (1.0, 0.5, 0.25):
            seq = full if scale == 1.0 else load_variant(
                c, f"x{scale}", lambda f, s=scale: cv2.resize(f, None, fx=s, fy=s, interpolation=cv2.INTER_AREA))
            ys = seq.landmarks[..., 1]
            person_px = float(np.nanmedian(np.nanmax(ys[:, BODY], 1) - np.nanmin(ys[:, BODY], 1)))
            found = float(np.mean(~np.isnan(seq.landmarks[:, 0, 0])))
            vis = float(np.nanmean(seq.landmarks[:, BODY, 2]))
            d = [100 * float(np.nanmean(np.abs(seq.world[:, BODY, k] - full.world[:, BODY, k]))) for k in range(3)]
            sa = angle_series(seq, c.hand)
            dk = float(np.nanmedian(np.abs(sa["front knee"] - fa["front knee"])))
            de = float(np.nanmedian(np.abs(sa["elbow"] - fa["elbow"])))
            print(f"  {cid:14s} x{scale:<4} person {person_px:5.0f}px found {100*found:3.0f}% vis {vis:.2f}  Δxyz {d[0]:4.1f}/{d[1]:4.1f}/{d[2]:4.1f} cm  knee Δ{dk:4.1f}° elbow Δ{de:4.1f}°")
            lines.append(f"| {cid} | ×{scale} | {person_px:.0f} | {100*found:.0f}% | {vis:.2f} | {d[0]:.1f} / {d[1]:.1f} / {d[2]:.1f} | {dk:.1f} | {de:.1f} |")

    REPORTS.mkdir(exist_ok=True)
    path = REPORTS / f"{stamp}.md"
    path.write_text("\n".join(lines) + "\n")
    print(f"\nreport: {path}")


if __name__ == "__main__":
    sys.exit(main())

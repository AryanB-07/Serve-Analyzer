"""Does the pipeline reject clips that aren't serves?

    python -m evaluation.negatives fetch   # download the non-serve videos (evaluation/labels/negative_clips.json)
    python -m evaluation.negatives         # score the serve check, writes evaluation/reports/serve_check_<time>.md

Each non-serve video is cut into 4-second windows, and each window stands for one
upload. A window counts as wrongly accepted if either hand would be accepted, since
the hand setting means nothing for a clip that isn't a serve. The same report checks
that every labelled real serve and every synthetic serve is still accepted, and that a
synthetic toss without a swing is rejected.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

import numpy as np

from serve_analyzer.config import AnalysisConfig
from serve_analyzer.models import Hand, PoseSequence
from serve_analyzer.phases import REJECTION_MESSAGES
from serve_analyzer.pipeline import measure_detailed
from serve_analyzer.pose import ensure_model, extract_pose_sequence
from serve_analyzer.video import probe

from . import real, synthetic
from .sweep import REPORTS, commit_id

LABELS = Path(__file__).parent / "labels" / "negative_clips.json"
CACHE = real.CACHE / "negatives"
WINDOW_S = 4.0


@dataclass(frozen=True)
class NegativeClip:
    id: str
    kind: str
    download: str

    @property
    def path(self) -> Path:
        return CACHE / "src" / Path(self.download).name.replace("%2C", ",")


def load_clips() -> list[NegativeClip]:
    raw = json.loads(LABELS.read_text())["clips"]
    return [NegativeClip(k, v["kind"], v["download"]) for k, v in raw.items()]


def fetch() -> None:
    for clip in load_clips():
        if clip.path.exists() and clip.path.stat().st_size > 10_000:
            continue
        clip.path.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {clip.id}")
        real._download(clip.download, clip.path)


def load_pose(clip: NegativeClip) -> PoseSequence:
    path = CACHE / "landmarks" / f"{clip.path.stem}.npz"
    if not path.exists():
        seq = extract_pose_sequence(probe(clip.path), ensure_model("heavy", AnalysisConfig().model_dir))
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, landmarks=seq.landmarks, world=seq.world, fps=seq.fps, width=seq.width, height=seq.height)
    d = np.load(path)
    return PoseSequence(d["landmarks"], float(d["fps"]), int(d["width"]), int(d["height"]), world=d["world"])


def windows(seq: PoseSequence) -> list[PoseSequence]:
    """Non-overlapping 4-second windows that contain a person."""
    w = round(WINDOW_S * seq.fps)
    out = []
    for start in range(0, max(seq.n_frames - w // 2, 1), w):
        sub = replace(seq, landmarks=seq.landmarks[start:start + w],
                      world=None if seq.world is None else seq.world[start:start + w])
        if not np.isnan(sub.landmarks[:, :, 0]).all():
            out.append(sub)
    return out


def score(cfg: AnalysisConfig) -> dict:
    by_kind: dict[str, list[bool]] = {}
    accepted_windows, reasons = [], Counter()
    for clip in load_clips():
        if not clip.path.exists():
            continue
        for i, win in enumerate(windows(load_pose(clip))):
            r = {h: measure_detailed(win, h, cfg).rejection for h in (Hand.RIGHT, Hand.LEFT)}
            reasons.update(r.values())
            accepted = any(v is None for v in r.values())
            by_kind.setdefault(clip.kind, []).append(accepted)
            if accepted:
                accepted_windows.append(f"{clip.id}#{i} ({', '.join(h.value for h, v in r.items() if v is None)} hand)")
    serves = [c for c in real.load_clips() if c.contact is not None]
    no_serve = [c for c in real.load_clips() if c.contact is None]
    lost = [c.id for c in serves if measure_detailed(real.load_pose(c), c.hand, cfg).rejection is not None]
    kept = [c.id for c in no_serve if measure_detailed(real.load_pose(c), c.hand, cfg).rejection is None]
    syn_lost = syn_swingless_kept = 0
    for spec in synthetic.SERVE_SPECS:
        for cam in synthetic.CAMERAS:
            syn_lost += measure_detailed(synthetic.film(synthetic.make_serve(spec), cam), spec.hand, cfg).rejection is not None
            swingless = synthetic.film(synthetic.make_serve(replace(spec, swing=False)), cam)
            syn_swingless_kept += measure_detailed(swingless, spec.hand, cfg).rejection is None
    n_syn = len(synthetic.SERVE_SPECS) * len(synthetic.CAMERAS)
    return {
        "by_kind": {k: (sum(v), len(v)) for k, v in by_kind.items()},
        "accepted": accepted_windows, "reasons": reasons,
        "real_serves": (len(serves) - len(lost), len(serves), lost),
        "no_serve_rejected": (len(no_serve) - len(kept), len(no_serve), kept),
        "synthetic_serves": (n_syn - syn_lost, n_syn), "synthetic_swingless_rejected": (n_syn - syn_swingless_kept, n_syn),
    }


def main() -> None:
    stamp = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{commit_id()}"
    results = {"toss + contact above the head (before)": score(AnalysisConfig(serve_shape_check=False)),
               "+ serve-shape checks (now)": score(AnalysisConfig())}
    kinds = sorted({k for r in results.values() for k in r["by_kind"]})
    lines = [f"# Serve check — {stamp}", "", "Lower is better for non-serve windows accepted; higher for everything else.", "",
             "| Check | " + " | ".join(f"{k} accepted" for k in kinds) + " | Real serves kept | No-serve real clips rejected "
             "| Synthetic serves kept | Synthetic toss-without-swing rejected |",
             "|---|" + "---|" * (len(kinds) + 4)]
    for name, r in results.items():
        cells = [f"{a}/{n}" for a, n in (r["by_kind"].get(k, (0, 0)) for k in kinds)]
        lines.append(f"| {name} | " + " | ".join(cells) + f" | {r['real_serves'][0]}/{r['real_serves'][1]} | "
                     f"{r['no_serve_rejected'][0]}/{r['no_serve_rejected'][1]} | {r['synthetic_serves'][0]}/{r['synthetic_serves'][1]} | "
                     f"{r['synthetic_swingless_rejected'][0]}/{r['synthetic_swingless_rejected'][1]} |")
    for name, r in results.items():
        lines += ["", f"## {name}", "", f"Non-serve windows still accepted: {', '.join(r['accepted']) or 'none'}", "",
                  f"Real serves rejected: {', '.join(r['real_serves'][2]) or 'none'}. "
                  f"No-serve clips accepted: {', '.join(r['no_serve_rejected'][2]) or 'none'}.", "",
                  "| Reason | Windows × hands |", "|---|---|"]
        lines += [f"| {REJECTION_MESSAGES.get(k, 'accepted') if k else 'accepted'} | {v} |" for k, v in r["reasons"].most_common()]
    path = REPORTS / f"serve_check_{stamp}.md"
    path.write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:6 + len(results)]))
    print(f"\nreport: {path}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "fetch":
        fetch()
    else:
        main()

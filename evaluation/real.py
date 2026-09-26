"""Real labelled clips: download/trim them and cache MediaPipe landmarks.

    python -m evaluation.real fetch     # download + trim into evaluation/.cache/clips
    python -m evaluation.real extract   # run MediaPipe once per clip, cache landmarks

Pose extraction is the slow step (about 15 ms per frame), so sweeps reuse the cache and
only re-run the cheap part of the pipeline for each configuration.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from serve_analyzer.config import AnalysisConfig
from serve_analyzer.models import Hand, PoseSequence
from serve_analyzer.pose import ensure_model, extract_pose_sequence
from serve_analyzer.video import iter_frames, open_writer, probe

ROOT = Path(__file__).resolve().parents[1]
LABELS = Path(__file__).parent / "labels" / "real_clips.json"
CACHE = Path(__file__).parent / ".cache"
USER_AGENT = "ServeAnalyzer-evaluation/0.1"


@dataclass(frozen=True)
class Clip:
    id: str
    view: str
    hand: Hand
    player: str
    trophy: int | None
    contact: int | None
    meta: dict

    @property
    def path(self) -> Path:
        return CACHE / "clips" / f"{self.id}.mp4"


def load_clips() -> list[Clip]:
    raw = json.loads(LABELS.read_text())["clips"]
    return [Clip(k, v["view"], Hand(v["hand"]), v["player"], v["trophy"], v["contact"], v) for k, v in raw.items()]


def _download(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request) as response, open(dest, "wb") as out:
        shutil.copyfileobj(response, out)


def fetch() -> None:
    (CACHE / "clips").mkdir(parents=True, exist_ok=True)
    downloads: dict[str, Path] = {}
    for clip in load_clips():
        if clip.path.exists():
            continue
        source = clip.meta["source"]
        if source.startswith("repo:"):
            shutil.copy(ROOT / source[5:], clip.path)
        else:
            url = clip.meta["download"]
            if url not in downloads:
                tmp = Path(tempfile.mkdtemp()) / "source"
                print(f"downloading {url}")
                _download(url, tmp)
                downloads[url] = tmp
            src = downloads[url]
            if "trim_s" in clip.meta:
                start, end = clip.meta["trim_s"]
                info = probe(src)
                frames = list(iter_frames(src))[int(start * info.fps):int(end * info.fps)]
                writer = open_writer(clip.path, info.fps, info.width, info.height)
                for f in frames:
                    writer.write(f)
                writer.release()
            else:
                shutil.copy(src, clip.path)
        print(f"ready {clip.id}")


def cache_path(clip: Clip, variant: str) -> Path:
    return CACHE / "landmarks" / f"{clip.id}.{variant}.npz"


def load_pose(clip: Clip, variant: str = "heavy") -> PoseSequence:
    """Cached MediaPipe output (2D landmarks + world landmarks) for a clip."""
    path = cache_path(clip, variant)
    if not path.exists():
        cfg = AnalysisConfig(model_variant=variant)
        seq = extract_pose_sequence(probe(clip.path), ensure_model(variant, cfg.model_dir))
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, landmarks=seq.landmarks, world=seq.world, fps=seq.fps, width=seq.width, height=seq.height)
    d = np.load(path)
    return PoseSequence(d["landmarks"], float(d["fps"]), int(d["width"]), int(d["height"]), world=d["world"])


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "fetch"
    if command == "fetch":
        fetch()
    elif command == "extract":
        for c in load_clips():
            seq = load_pose(c)
            print(f"{c.id}: {seq.n_frames} frames cached")
    else:
        raise SystemExit(f"unknown command {command}")

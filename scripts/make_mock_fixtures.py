"""Generate frontend mock-mode fixtures by running the real pipeline.

Writes frontend/public/mock/<id>/ with API-shaped summary.json and result.json
(built with the same conversion code the API uses) plus frames.json, videos
and a thumbnail. A second analysis is made from the clip with its first
frames cut off, so its phases fall on different frames (useful for compare).
"""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from serve_analyzer.pipeline import analyze
from serve_analyzer.video import iter_frames, open_writer, probe
from serve_api import keys
from serve_api.convert import counts_from_labels, result_from_file, summary_from_row

ROOT = Path(__file__).resolve().parents[1]
CLIP = ROOT / "tests" / "fixtures" / "sample_serve.mp4"
OUT = ROOT / "frontend" / "public" / "mock"
TRIM_FRAMES = 20
COPIED = [keys.FRAMES, keys.PLAYBACK, keys.ANNOTATED, keys.THUMBNAIL]


def trimmed_copy(src: Path, dst: Path, skip: int) -> Path:
    info = probe(src)
    writer = open_writer(dst, info.fps, info.width, info.height)
    for i, frame in enumerate(iter_frames(src)):
        if i >= skip:
            writer.write(frame)
    writer.release()
    return dst


def build(analysis_id: str, video: Path, filename: str, created_at: datetime) -> dict:
    def url_for(key: str) -> str:
        return f"/mock/{analysis_id}/{Path(key).name}"

    dest = OUT / analysis_id
    with tempfile.TemporaryDirectory() as tmp:
        analyze(video, "right", tmp)
        results = json.loads((Path(tmp) / keys.RESULTS).read_text())
        dest.mkdir(parents=True, exist_ok=True)
        for name in COPIED:
            shutil.copy(Path(tmp) / name, dest / name)

    result = result_from_file(analysis_id, results, url_for)
    row = {
        "id": analysis_id, "hand": "right", "status": "succeeded", "filename": filename,
        "created_at": created_at.isoformat(), "updated_at": created_at.isoformat(),
        "error_code": None, "error_message": None,
        "counts": json.dumps(counts_from_labels(results["labels"])),
    }
    summary = summary_from_row(row, url_for)
    (dest / "result.json").write_text(result.model_dump_json(indent=2) + "\n")
    (dest / "summary.json").write_text(summary.model_dump_json(indent=2) + "\n")
    return summary.model_dump(mode="json")


def main() -> None:
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    now = datetime(2026, 9, 20, 17, 30, tzinfo=UTC)
    with tempfile.TemporaryDirectory() as tmp:
        trimmed = trimmed_copy(CLIP, Path(tmp) / "trimmed.mp4", TRIM_FRAMES)
        summaries = [
            build("demo-serve-2", trimmed, "serve_week2.mp4", now),
            build("demo-serve-1", CLIP, "serve_week1.mp4", now - timedelta(days=7)),
        ]
    (OUT / "analyses.json").write_text(
        json.dumps({"items": summaries, "next_cursor": None}, indent=2) + "\n"
    )
    print(f"wrote fixtures for {[s['id'] for s in summaries]} to {OUT}")


if __name__ == "__main__":
    main()

"""Turn database rows and pipeline output files into API response models."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from typing import Any

from . import keys
from .schemas import AnalysisResult, AnalysisSummary, ApiError, StatusCounts

UrlFor = Callable[[str], str]

PUBLIC_MESSAGES = {
    "UNREADABLE_VIDEO": "We couldn't read this video file. Try exporting it as MP4.",
    "NO_PERSON_DETECTED": "We couldn't detect a person clearly. Check the filming guide.",
    "INTERNAL": "Something went wrong while analysing this video.",
}


def public_message(code: str, detail: str) -> str:
    """Pipeline messages for these codes can contain server paths, so replace them."""
    return PUBLIC_MESSAGES.get(code, detail)


def counts_from_labels(labels: dict[str, dict[str, str]]) -> dict[str, int]:
    tally = Counter(status for by_metric in labels.values() for status in by_metric.values())
    return {s: tally.get(s, 0) for s in ("good", "borderline", "off", "unknown")}


def summary_from_row(row: dict[str, Any], url_for: UrlFor) -> AnalysisSummary:
    succeeded = row["status"] == "succeeded"
    return AnalysisSummary(
        id=row["id"],
        hand=row["hand"],
        status=row["status"],
        filename=row["filename"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        error=ApiError(code=row["error_code"], message=row["error_message"] or "")
        if row["error_code"] else None,
        thumbnail_url=url_for(keys.output_key(row["id"], keys.THUMBNAIL)) if succeeded else None,
        counts=StatusCounts(**json.loads(row["counts"])) if row["counts"] else None,
    )


def result_from_file(analysis_id: str, results: dict[str, Any], url_for: UrlFor) -> AnalysisResult:
    """``results`` is the pipeline's results.json content."""
    return AnalysisResult(
        id=analysis_id,
        hand=results["hand"],
        fps=results["fps"],
        n_frames=results["n_frames"],
        width=results["width"],
        height=results["height"],
        phases=results["phases"],
        metrics=results["metrics"],
        labels=results["labels"],
        ranges=results["ranges"],
        feedback=results["feedback"],
        warnings=results["warnings"],
        video_url=url_for(keys.output_key(analysis_id, keys.PLAYBACK)),
        annotated_video_url=url_for(keys.output_key(analysis_id, keys.ANNOTATED)),
        thumbnail_url=url_for(keys.output_key(analysis_id, keys.THUMBNAIL)),
    )

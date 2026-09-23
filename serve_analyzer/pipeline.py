"""End-to-end analysis: video in, results.json (and annotated video) out."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import angles as A
from . import feedback, landmarks
from .config import AnalysisConfig
from .metrics import compute_metrics
from .models import AnalysisResult, Hand, PhaseFrames, PoseSequence
from .phases import detect_phases
from .pose import ensure_model, extract_pose_sequence
from .preprocessing import clean
from .reference import RangeTable, assess, load_ranges, to_labels
from .video import probe, validate


class AnalysisError(RuntimeError):
    """The video was valid but could not be analysed (e.g. no person found)."""


@dataclass
class SequenceAnalysis:
    result: AnalysisResult
    pose: PoseSequence
    series: A.Series


def analyze_sequence(
    raw: PoseSequence, hand: Hand, config: AnalysisConfig, ranges: RangeTable
) -> SequenceAnalysis:
    """Everything after pose extraction. Pure: no file or video I/O."""
    if np.isnan(raw.landmarks[:, :, :2]).all():
        raise AnalysisError("No person was detected in the video.")

    pose = clean(
        raw,
        config.visibility_threshold,
        config.max_gap_frames,
        config.smoothing_window_ms if config.smoothing_enabled else None,
        config.smoothing_polyorder,
    )
    series = A.compute_series(pose, hand)
    phases = detect_phases(series)
    metrics = compute_metrics(series, phases)
    assessments = assess(metrics, ranges)

    result = AnalysisResult(
        hand=hand,
        fps=raw.fps,
        n_frames=raw.n_frames,
        phases=phases,
        metrics=metrics,
        labels=to_labels(assessments),
        feedback=feedback.generate(assessments),
        warnings=_warnings(phases, raw.n_frames, hand),
    )
    return SequenceAnalysis(result, pose, series)


EDGE_FRAMES = 2


def _warnings(phases: PhaseFrames, n_frames: int, hand: Hand) -> list[str]:
    out = []
    for name, frame in phases.as_dict().items():
        if frame is None:
            out.append(f"Could not detect the {name.replace('_', ' ')} phase.")
    contact = phases.contact
    if contact is not None and (contact < EDGE_FRAMES or contact >= n_frames - EDGE_FRAMES):
        other = Hand.LEFT if hand is Hand.RIGHT else Hand.RIGHT
        out.append(
            "The hitting wrist is highest at the very edge of the clip, so contact may be "
            f"cut off or --hand may be wrong (try --hand {other.value})."
        )
    return out


def analyze(
    video_path: str | Path,
    hand: Hand | str,
    out_dir: str | Path,
    config: AnalysisConfig | None = None,
    debug_plots: bool = False,
    render_video: bool = True,
) -> AnalysisResult:
    """Validate, extract pose, analyse, and write outputs into ``out_dir``."""
    config = config or AnalysisConfig()
    hand = Hand(hand)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    info = probe(video_path)
    validate(info, config.max_duration_s, config.min_fps)
    ranges = load_ranges(config.reference_ranges_path)

    model_path = ensure_model(config.model_variant, config.model_dir)
    raw = extract_pose_sequence(info, model_path)
    analysis = analyze_sequence(raw, hand, config, ranges)
    result = analysis.result

    if debug_plots:
        from .plots import plot_smoothing

        unsmoothed = clean(raw, config.visibility_threshold, config.max_gap_frames, None)
        wrist = landmarks.hitting_arm(hand).wrist
        path = plot_smoothing(
            unsmoothed, analysis.pose, wrist, f"Hitting wrist ({hand.value})",
            out_dir / "smoothing_wrist.png",
        )
        result.outputs["smoothing_plot"] = str(path)

    if render_video:
        from .render import render_annotated

        video_out = render_annotated(
            info.path, analysis.pose, analysis.series, result.phases, hand,
            out_dir / "annotated.mp4",
        )
        result.outputs["annotated_video"] = str(video_out)

    results_path = out_dir / "results.json"
    result.outputs["results"] = str(results_path)
    results_path.write_text(json.dumps(result.to_dict(), indent=2))
    return result

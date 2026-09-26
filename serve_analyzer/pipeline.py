"""End-to-end analysis: video in, results.json, frames.json and videos out."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

from . import angles as A
from . import feedback, landmarks
from .config import AnalysisConfig
from .errors import AnalysisError
from .export import build_frames_payload
from .metrics import compute_metrics
from .models import AnalysisResult, Hand, PhaseFrames, PoseSequence
from .phases import detect_phases
from .pose import ensure_model, extract_pose_sequence
from .preprocessing import clean
from .reference import RangeTable, assess, load_ranges, ranges_to_dict, to_labels
from .video import probe, validate, write_playback_copy, write_thumbnail

__all__ = ["AnalysisError", "SequenceAnalysis", "Stage", "analyze", "analyze_sequence"]

Stage = Literal["extracting_pose", "analyzing", "rendering"]

RESULTS_FILE = "results.json"
FRAMES_FILE = "frames.json"
PLAYBACK_FILE = "playback.mp4"
ANNOTATED_FILE = "annotated.mp4"
THUMBNAIL_FILE = "thumbnail.jpg"

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
        raise AnalysisError("No person was detected in the video.", code="NO_PERSON_DETECTED")

    pose, series, phases = measure(raw, hand, config)
    metrics = compute_metrics(series, phases)
    assessments = assess(metrics, ranges)

    result = AnalysisResult(
        hand=hand,
        fps=raw.fps,
        n_frames=raw.n_frames,
        width=raw.width,
        height=raw.height,
        phases=phases,
        metrics=metrics,
        labels=to_labels(assessments),
        ranges=ranges_to_dict(ranges),
        feedback=feedback.generate(assessments),
        warnings=_warnings(phases, raw.n_frames, hand, config.require_complete_serve),
    )
    return SequenceAnalysis(result, pose, series)


def measure(
    raw: PoseSequence, hand: Hand, config: AnalysisConfig
) -> tuple[PoseSequence, A.Series, PhaseFrames]:
    """Clean the landmarks, compute the per-frame series and detect the phases.

    Phases are timed from ``phase_signal_space`` series (2D by default: on real
    MediaPipe output the 2D knee curve times the trophy better, even when the
    3D angles measure its size better). Contact can use its own, looser
    visibility threshold, because only the wrist's height matters there.
    """
    window_ms = config.smoothing_window_ms if config.smoothing_enabled else None

    def cleaned(threshold: float) -> PoseSequence:
        return clean(raw, threshold, config.max_gap_frames, window_ms, config.smoothing_polyorder)

    pose = cleaned(config.visibility_threshold)
    series = A.compute_series(pose, hand, config.angle_space)
    if config.phase_signal_space == "image2d" and config.angle_space != "image2d":
        phase_series = A.compute_series(pose, hand, "image2d")
    else:
        phase_series = series
    contact_series = None
    ct = config.contact_visibility_threshold
    if ct is not None and ct != config.visibility_threshold:
        contact_series = A.compute_series(cleaned(ct), hand, "image2d")
    window = round(config.trophy_window_s * raw.fps) if config.trophy_window_s else None
    phases = detect_phases(
        phase_series, config.trophy_method, config.racket_drop_method, config.require_complete_serve,
        window, config.trophy_fallback, contact_series, config.trophy_plateau_deg,
    )
    return pose, series, phases


EDGE_FRAMES = 2


def _warnings(
    phases: PhaseFrames, n_frames: int, hand: Hand, require_complete_serve: bool = False
) -> list[str]:
    if require_complete_serve and phases.contact is None:
        return [
            "We couldn't find a complete serve (a toss and then contact above the head) "
            "in this clip. Make sure the clip runs until just after contact."
        ]
    out = []
    for name, frame in phases.as_dict().items():
        if frame is None:
            out.append(f"Could not detect the {name.replace('_', ' ')} phase.")
    contact = phases.contact
    if contact is not None and (contact < EDGE_FRAMES or contact >= n_frames - EDGE_FRAMES):
        other = Hand.LEFT if hand is Hand.RIGHT else Hand.RIGHT
        out.append(
            "The hitting wrist is highest at the very edge of the clip, so contact may be "
            f"cut off or the hitting hand may be wrong (try {other.value})."
        )
    return out


def _thumbnail_frame(phases: PhaseFrames, n_frames: int) -> int:
    for frame in (phases.trophy, phases.contact):
        if frame is not None:
            return frame
    return n_frames // 2


def analyze(
    video_path: str | Path,
    hand: Hand | str,
    out_dir: str | Path,
    config: AnalysisConfig | None = None,
    debug_plots: bool = False,
    render_video: bool = True,
    on_stage: Callable[[Stage], None] | None = None,
) -> AnalysisResult:
    """Validate, extract pose, analyse, and write outputs into ``out_dir``.

    ``on_stage`` is called as each stage starts, for progress reporting.
    """
    config = config or AnalysisConfig()
    hand = Hand(hand)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = on_stage or (lambda stage: None)

    info = probe(video_path)
    validate(info, config.max_duration_s, config.min_fps)
    ranges = load_ranges(config.reference_ranges_path)

    report("extracting_pose")
    model_path = ensure_model(config.model_variant, config.model_dir)
    raw = extract_pose_sequence(info, model_path)

    report("analyzing")
    analysis = analyze_sequence(raw, hand, config, ranges)
    result = analysis.result

    frames_path = out_dir / FRAMES_FILE
    frames_path.write_text(
        json.dumps(
            build_frames_payload(raw, analysis.pose, analysis.series, result.phases),
            separators=(",", ":"),
        )
    )
    result.outputs["frames"] = str(frames_path)

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

        report("rendering")
        result.outputs["playback_video"] = str(
            write_playback_copy(info.path, out_dir / PLAYBACK_FILE, info.fps)
        )
        result.outputs["annotated_video"] = str(
            render_annotated(
                info.path, analysis.pose, analysis.series, result.phases, hand,
                out_dir / ANNOTATED_FILE,
            )
        )
        result.outputs["thumbnail"] = str(
            write_thumbnail(
                info.path, _thumbnail_frame(result.phases, result.n_frames),
                out_dir / THUMBNAIL_FILE,
            )
        )

    results_path = out_dir / RESULTS_FILE
    result.outputs["results"] = str(results_path)
    results_path.write_text(json.dumps(result.to_dict(), indent=2))
    return result

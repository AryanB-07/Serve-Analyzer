"""End-to-end analysis: video in, results.json, frames.json and videos out."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NamedTuple

import numpy as np

from . import angles as A
from . import feedback, landmarks
from .config import AnalysisConfig
from .errors import AnalysisError
from .export import build_frames_payload
from .metrics import compute_metrics
from .models import AnalysisResult, Hand, PhaseFrames, PoseSequence, VideoInfo
from .outputs import ANNOTATED_FILE, FRAMES_FILE, PLAYBACK_FILE, RESULTS_FILE, THUMBNAIL_FILE
from .phases import REJECTION_MESSAGES, detect_contact, detect_phases, serve_rejection
from .pose import ensure_model, extract_pose_sequence
from .preprocessing import clean
from .reference import RangeTable, assess, load_ranges, ranges_to_dict, to_labels
from .video import probe_or_convert, validate, write_playback_copy, write_thumbnail

__all__ = ["AnalysisError", "SequenceAnalysis", "Stage", "analyze", "analyze_sequence"]

Stage = Literal["extracting_pose", "analyzing", "rendering"]
PoseExtractor = Callable[[VideoInfo, Path], PoseSequence]


@dataclass
class SequenceAnalysis:
    result: AnalysisResult
    pose: PoseSequence
    series: A.Series

def analyze_sequence(
    raw: PoseSequence, hand: Hand, config: AnalysisConfig, ranges: RangeTable,
    expected_frames: int | None = None,
) -> SequenceAnalysis:
    """Everything after pose extraction. Pure: no file or video I/O.

    ``expected_frames`` is the frame count the file's header promises; reading far fewer
    means the file is cut off, which gets a warning."""
    if np.isnan(raw.landmarks[:, :, :2]).all():
        raise AnalysisError("No person was detected in the video.", code="NO_PERSON_DETECTED")

    m = measure_detailed(raw, hand, config)
    if m.rejection is not None:
        raise AnalysisError(
            f"This doesn't look like a serve. {REJECTION_MESSAGES[m.rejection]}", code="NOT_A_SERVE"
        )
    pose, series, phases = m.pose, m.series, m.phases
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
        warnings=_warnings(phases, raw.n_frames, hand, expected_frames),
    )
    return SequenceAnalysis(result, pose, series)


class Measurement(NamedTuple):
    pose: PoseSequence
    series: A.Series
    phases: PhaseFrames
    rejection: str | None  # why the clip isn't a serve (a REJECTION_MESSAGES key), or None


def measure(
    raw: PoseSequence, hand: Hand, config: AnalysisConfig
) -> tuple[PoseSequence, A.Series, PhaseFrames]:
    """``measure_detailed`` without the rejection reason; rejected clips have no phases."""
    m = measure_detailed(raw, hand, config)
    return m.pose, m.series, m.phases


def measure_detailed(raw: PoseSequence, hand: Hand, config: AnalysisConfig) -> Measurement:
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
    slow = config.trophy_window_min_swing_speed
    if window is not None and slow is not None and phases.contact is not None:
        speed = swing_speed(pose, hand, phases.contact)
        if speed is not None and speed < slow:
            phases = detect_phases(
                phase_series, config.trophy_method, config.racket_drop_method, config.require_complete_serve,
                round(window * slow / speed), config.trophy_fallback, contact_series, config.trophy_plateau_deg,
            )
    rejection = None
    if config.require_complete_serve:
        cs = contact_series if contact_series is not None else phase_series
        contact = detect_contact(cs[A.WRIST_ELEVATION_PX])
        if phases.contact is None:
            tossed = contact is not None and bool(
                (np.nan_to_num(phase_series[A.TOSS_ARM_RAISE_PX][:contact], nan=-np.inf) > 0).any()
            )
            rejection = "no_contact" if contact is None else ("wrist_not_above_head" if tossed else "no_toss")
        elif config.serve_shape_check:
            rejection = serve_rejection(cs, phases.contact, raw.fps)
        if rejection is not None:
            phases = PhaseFrames()
    return Measurement(pose, series, phases, rejection)


def swing_speed(pose: PoseSequence, hand: Hand, contact: int) -> float | None:
    """Peak speed of the hitting wrist just before contact, in torso lengths per second.

    Real-time serves measure 11-32 on the evaluation clips; slow-motion replays far less,
    which is how ``trophy_window_min_swing_speed`` recognises them.
    """
    arm = landmarks.hitting_arm(hand)
    hip = landmarks.LEFT_HIP if arm.shoulder == landmarks.LEFT_SHOULDER else landmarks.RIGHT_HIP
    xy = pose.landmarks[:, :, :2]
    torso = np.nanmedian(np.linalg.norm(xy[:, arm.shoulder] - xy[:, hip], axis=1))
    lo, hi = max(0, contact - round(0.5 * pose.fps)), min(pose.n_frames, contact + round(0.2 * pose.fps) + 1)
    step = np.linalg.norm(np.diff(xy[lo:hi, arm.wrist], axis=0), axis=1)
    if not np.isfinite(torso) or torso <= 0 or np.isnan(step).all():
        return None
    return float(np.nanmax(step)) * pose.fps / float(torso)


EDGE_FRAMES = 2


TRUNCATED_BELOW = 0.9  # of the header's frame count


def _warnings(
    phases: PhaseFrames, n_frames: int, hand: Hand, expected_frames: int | None = None
) -> list[str]:
    out = []
    if expected_frames and n_frames < TRUNCATED_BELOW * expected_frames:
        out.append(
            f"Only {n_frames} of the video's {expected_frames} frames could be read, so the file "
            "looks incomplete. If the serve seems cut off, upload the original file again."
        )
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
    pose_extractor: PoseExtractor | None = None,
) -> AnalysisResult:
    """Validate, extract pose, analyse, and write outputs into ``out_dir``.

    ``on_stage`` is called as each stage starts, for progress reporting. ``pose_extractor``
    replaces ``extract_pose_sequence``; the worker passes ``extract_pose_in_subprocess`` so
    MediaPipe's memory is released after each video.
    """
    config = config or AnalysisConfig()
    hand = Hand(hand)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = on_stage or (lambda stage: None)

    # A converted copy (for formats OpenCV can't decode) lives here, outside out_dir.
    with tempfile.TemporaryDirectory(prefix="serve-analyzer-") as scratch:
        info = probe_or_convert(video_path, scratch)
        return _analyze_video(info, hand, out_dir, config, debug_plots, render_video, report,
                              pose_extractor or extract_pose_sequence)


def _analyze_video(
    info: VideoInfo, hand: Hand, out_dir: Path, config: AnalysisConfig, debug_plots: bool,
    render_video: bool, report: Callable[[Stage], None], pose_extractor: PoseExtractor,
) -> AnalysisResult:
    validate(info, config.max_duration_s, config.min_fps)
    ranges = load_ranges(config.reference_ranges_path)

    report("extracting_pose")
    model_path = ensure_model(config.model_variant, config.model_dir)
    raw = pose_extractor(info, model_path)

    report("analyzing")
    analysis = analyze_sequence(raw, hand, config, ranges, expected_frames=info.frame_count)
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

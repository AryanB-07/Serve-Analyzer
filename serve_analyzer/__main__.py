"""Command-line entry point: ``python -m serve_analyzer analyze VIDEO --hand right``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import AnalysisConfig
from .models import Hand
from .pipeline import AnalysisError, analyze
from .video import VideoValidationError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="serve_analyzer")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("analyze", help="Analyse one serve video")
    p.add_argument("video", type=Path)
    p.add_argument("--hand", choices=[h.value for h in Hand], required=True)
    p.add_argument("--out", type=Path, default=Path("results"))
    p.add_argument("--ranges", type=Path, help="custom reference_ranges.json")
    p.add_argument("--smooth-ms", type=float, default=AnalysisConfig.smoothing_window_ms,
                   help="Savitzky-Golay window in ms; 0 disables smoothing")
    p.add_argument("--model", choices=["lite", "full", "heavy"], default="heavy")
    p.add_argument("--debug-plots", action="store_true",
                   help="also save a before/after smoothing plot (needs matplotlib)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = AnalysisConfig(
        model_variant=args.model,
        smoothing_enabled=args.smooth_ms > 0,
        smoothing_window_ms=args.smooth_ms,
        reference_ranges_path=args.ranges,
    )
    try:
        result = analyze(args.video, args.hand, args.out, config, debug_plots=args.debug_plots)
    except (VideoValidationError, AnalysisError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    phases = ", ".join(f"{k}={v}" for k, v in result.phases.as_dict().items())
    print(f"Phases (frame): {phases}")
    print("Feedback:")
    for point in result.feedback:
        print(f"  - {point}")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for name, path in result.outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

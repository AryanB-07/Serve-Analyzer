"""Command-line entry point: ``python -m serve_analyzer analyze VIDEO --hand right``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import AnalysisConfig
from .models import Hand
from .video import VideoValidationError, probe, validate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="serve_analyzer")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="Analyse one serve video")
    analyze.add_argument("video", type=Path)
    analyze.add_argument("--hand", choices=[h.value for h in Hand], required=True)
    analyze.add_argument("--out", type=Path, default=Path("results"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = AnalysisConfig()
    try:
        info = probe(args.video)
        validate(info, config.max_duration_s, config.min_fps)
    except VideoValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"{info.path.name}: {info.width}x{info.height}, {info.fps:.1f} fps, {info.duration_s:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())

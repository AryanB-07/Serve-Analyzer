"""Diagnostic plots. Requires the optional ``dev`` extra (matplotlib)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .models import PoseSequence

BEFORE_COLOR = "#a3a29c"
AFTER_COLOR = "#2a78d6"
TEXT_COLOR = "#52514e"
GRID_COLOR = "#e6e5e0"


def plot_smoothing(
    before: PoseSequence, after: PoseSequence, landmark: int, name: str, path: Path
) -> Path:
    """Save a two-panel (x, y) plot of one landmark before and after smoothing."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = np.arange(before.n_frames) / before.fps
    fig, axes = plt.subplots(2, 1, figsize=(9, 5.5), sharex=True, constrained_layout=True)
    for ax, coord, label in zip(axes, (0, 1), ("x (px)", "y (px, up is up)")):
        ax.plot(t, before.landmarks[:, landmark, coord], color=BEFORE_COLOR, lw=1.2,
                marker="o", ms=3, label="Before (interpolated, unsmoothed)")
        ax.plot(t, after.landmarks[:, landmark, coord], color=AFTER_COLOR, lw=2,
                label="After Savitzky–Golay")
        ax.set_ylabel(label, color=TEXT_COLOR)
        ax.grid(True, color=GRID_COLOR, lw=0.8)
        ax.tick_params(colors=TEXT_COLOR)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[1].invert_yaxis()
    axes[1].set_xlabel("time (s)", color=TEXT_COLOR)
    axes[0].legend(frameon=False, loc="best")
    fig.suptitle(f"{name} trajectory: effect of smoothing", color="#0b0b0b")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path

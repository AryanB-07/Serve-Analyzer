"""Annotated output video: skeleton, current phase and key angles."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from . import angles as A
from . import landmarks as L
from .models import Hand, PhaseFrames, PoseSequence
from .phases import phase_label
from .video import iter_frames, open_writer

# BGR
BODY_COLOR = (40, 215, 255)
HIT_COLOR = (214, 120, 42)
JOINT_COLOR = (40, 40, 40)
EVENT_COLOR = (52, 104, 235)

EVENT_NAMES = {"trophy": "TROPHY", "racket_drop": "RACKET DROP", "contact": "CONTACT"}
EVENT_HOLD_S = 0.3

OVERLAY = [
    (A.ELBOW_ANGLE, "Elbow", "{:.0f} deg"),
    (A.FRONT_KNEE_FLEXION, "Front knee", "{:.0f} deg"),
    (A.BACK_KNEE_FLEXION, "Back knee", "{:.0f} deg"),
    (A.TRUNK_TILT, "Trunk tilt", "{:.0f} deg"),
    (A.WRIST_HEIGHT, "Wrist height", "{:.2f}"),
]


def _text(img: np.ndarray, text: str, org: tuple[int, int], scale: float,
          color=(255, 255, 255), thickness: int = 1) -> None:
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def _point(xy: np.ndarray) -> tuple[int, int] | None:
    return None if np.isnan(xy).any() else (int(round(xy[0])), int(round(xy[1])))


def _draw_skeleton(img: np.ndarray, pts: np.ndarray, hand: Hand, lw: int) -> None:
    hit = L.hitting_arm(hand)
    hit_edges = {(hit.shoulder, hit.elbow), (hit.elbow, hit.wrist)}
    for a, b in L.SKELETON_EDGES:
        pa, pb = _point(pts[a]), _point(pts[b])
        if pa and pb:
            color = HIT_COLOR if (a, b) in hit_edges else BODY_COLOR
            cv2.line(img, pa, pb, color, lw + (1 if color == HIT_COLOR else 0), cv2.LINE_AA)
    used = {j for edge in L.SKELETON_EDGES for j in edge} | {L.NOSE}
    for j in used:
        p = _point(pts[j])
        if p:
            cv2.circle(img, p, lw + 1, JOINT_COLOR, -1, cv2.LINE_AA)
            cv2.circle(img, p, lw + 1, BODY_COLOR, 1, cv2.LINE_AA)


def _draw_panel(img: np.ndarray, lines: list[str], scale: float) -> None:
    line_h = int(28 * scale) + 6
    pad = int(8 * scale) + 4
    width = int(max(cv2.getTextSize(t, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)[0][0] for t in lines)) + 2 * pad
    height = line_h * len(lines) + pad
    roi = img[0:height, 0:width]
    img[0:height, 0:width] = (roi * 0.45).astype(img.dtype)
    for i, t in enumerate(lines):
        _text(img, t, (pad, pad + line_h * i + int(18 * scale)), scale, thickness=1 if i else 2)


def _current_event(frame: int, phases: PhaseFrames, hold: int) -> str | None:
    for attr, name in EVENT_NAMES.items():
        start = getattr(phases, attr)
        if start is not None and start <= frame < start + hold:
            return name
    return None


def render_annotated(
    video_path: str | Path,
    pose: PoseSequence,
    series: A.Series,
    phases: PhaseFrames,
    hand: Hand,
    out_path: str | Path,
) -> Path:
    out_path = Path(out_path)
    scale = max(pose.height / 720, 0.45)
    lw = max(int(round(3 * scale)), 2)
    hold = max(int(round(EVENT_HOLD_S * pose.fps)), 1)

    writer = open_writer(out_path, pose.fps, pose.width, pose.height)
    try:
        for i, frame in enumerate(iter_frames(video_path)):
            if i < pose.n_frames:
                _draw_skeleton(frame, pose.landmarks[i, :, :2], hand, lw)
                lines = [phase_label(i, phases)]
                for key, label, fmt in OVERLAY:
                    v = series[key][i]
                    lines.append(f"{label}: {'--' if np.isnan(v) else fmt.format(v)}")
                _draw_panel(frame, lines, scale * 0.9)

                event = _current_event(i, phases, hold)
                if event:
                    cv2.rectangle(frame, (0, 0), (pose.width - 1, pose.height - 1), EVENT_COLOR, lw * 2)
                    size = cv2.getTextSize(event, cv2.FONT_HERSHEY_SIMPLEX, scale * 1.4, 3)[0]
                    _text(frame, event, ((pose.width - size[0]) // 2, pose.height - int(30 * scale)),
                          scale * 1.4, EVENT_COLOR, 3)
            writer.write(frame)
    finally:
        writer.release()
    return out_path

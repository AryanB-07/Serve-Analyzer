import type { PhaseFrames, PhaseName } from "../api/types";
import { SEGMENT_ORDER, type Segment } from "./phases";
import { clampFrame } from "./time";

export interface TimelineSegment {
  segment: Segment;
  /** First frame (inclusive). */
  start: number;
  /** One past the last frame (exclusive). */
  end: number;
}

export interface PhaseMarker {
  phase: PhaseName;
  frame: number;
}

const PHASES: PhaseName[] = ["trophy", "racket_drop", "contact"];

/** Detected phase events, in frame order. */
export function phaseMarkers(phases: PhaseFrames): PhaseMarker[] {
  return PHASES.flatMap((phase) => {
    const frame = phases[phase];
    return frame === null ? [] : [{ phase, frame }];
  }).sort((a, b) => a.frame - b.frame);
}

/**
 * Contiguous segments covering [0, nFrames): stance until the first detected
 * phase, then each phase until the next one. Undetected phases get no
 * segment; zero-length segments are dropped.
 */
export function timelineSegments(phases: PhaseFrames, nFrames: number): TimelineSegment[] {
  const starts: { segment: Segment; start: number }[] = [{ segment: "stance", start: 0 }];
  for (const { phase, frame } of phaseMarkers(phases)) {
    starts.push({ segment: phase, start: clampFrame(frame, nFrames) });
  }
  const out: TimelineSegment[] = [];
  starts.forEach(({ segment, start }, i) => {
    const end = i + 1 < starts.length ? starts[i + 1]!.start : nFrames;
    if (end > start) out.push({ segment, start, end });
  });
  return out.sort((a, b) => SEGMENT_ORDER.indexOf(a.segment) - SEGMENT_ORDER.indexOf(b.segment));
}

/** Frame under a horizontal position (0 = left edge, 1 = right edge). */
export function frameAtFraction(fraction: number, nFrames: number): number {
  return clampFrame(Math.floor(fraction * nFrames), nFrames);
}

/** Horizontal centre of a frame's slot, as a fraction of the track. */
export function fractionForFrame(frame: number, nFrames: number): number {
  return nFrames > 0 ? (clampFrame(frame, nFrames) + 0.5) / nFrames : 0;
}

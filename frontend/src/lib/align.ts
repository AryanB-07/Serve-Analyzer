import type { PhaseFrames, PhaseName } from "../api/types";
import { clampFrame, frameAtTime } from "./time";

export interface ClipTiming {
  phases: PhaseFrames;
  fps: number;
  nFrames: number;
}

/** A pair of matching moments, in seconds, in clip A and clip B. */
export interface Anchor {
  a: number;
  b: number;
}

export interface PhaseAnchor extends Anchor {
  phase: PhaseName;
}

const PHASE_ORDER = ["trophy", "racket_drop", "contact"] as const;

/**
 * Phase events detected in both clips. Pairs that would run time backwards
 * in either clip (inconsistent detections) are dropped so the warp stays
 * monotonic.
 */
export function phaseAnchors(a: ClipTiming, b: ClipTiming): PhaseAnchor[] {
  const out: PhaseAnchor[] = [];
  for (const phase of PHASE_ORDER) {
    const fa = a.phases[phase];
    const fb = b.phases[phase];
    if (fa === null || fb === null) continue;
    const anchor = { phase, a: fa / a.fps, b: fb / b.fps };
    const prev = out.at(-1);
    if (prev && (anchor.a <= prev.a || anchor.b <= prev.b)) continue;
    out.push(anchor);
  }
  return out;
}

/**
 * Map a time in A to the matching time in B: linear between anchors,
 * real-time (slope 1) outside them. With no anchors it is the identity.
 */
export function mapTime(tA: number, anchors: Anchor[]): number {
  const first = anchors[0];
  const last = anchors.at(-1);
  if (!first || !last) return tA;
  if (tA <= first.a) return first.b + (tA - first.a);
  if (tA >= last.a) return last.b + (tA - last.a);
  for (let i = 0; i + 1 < anchors.length; i++) {
    const p = anchors[i]!;
    const q = anchors[i + 1]!;
    if (tA <= q.a) return p.b + ((tA - p.a) * (q.b - p.b)) / (q.a - p.a);
  }
  return tA;
}

/** How fast B must play relative to A at this moment. */
export function slopeAt(tA: number, anchors: Anchor[]): number {
  for (let i = 0; i + 1 < anchors.length; i++) {
    const p = anchors[i]!;
    const q = anchors[i + 1]!;
    if (tA >= p.a && tA < q.a) return (q.b - p.b) / (q.a - p.a);
  }
  return 1;
}

export interface MappedFrame {
  frame: number;
  /** True when A's moment falls before B's first frame or after its last. */
  outside: boolean;
}

/** The B frame shown alongside A's frame. */
export function mapFrame(frameA: number, a: ClipTiming, b: ClipTiming, anchors: Anchor[]): MappedFrame {
  const tB = mapTime(frameA / a.fps, anchors);
  const lastB = (b.nFrames - 1) / b.fps;
  const outside = tB < -0.5 / b.fps || tB > lastB + 0.5 / b.fps;
  return { frame: clampFrame(frameAtTime(Math.max(0, tB), b.fps, b.nFrames), b.nFrames), outside };
}

/** B's per-frame series re-indexed onto A's frames, for overlaid charts. */
export function resampleOnto(
  seriesB: readonly (number | null)[],
  a: ClipTiming,
  b: ClipTiming,
  anchors: Anchor[],
): (number | null)[] {
  return Array.from({ length: a.nFrames }, (_, i) => {
    const { frame, outside } = mapFrame(i, a, b, anchors);
    return outside ? null : (seriesB[frame] ?? null);
  });
}

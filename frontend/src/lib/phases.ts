import type { PhaseFrames, PhaseName } from "../api/types";

/** Timeline segments: the stretch of the serve from one phase event to the next. */
export type Segment = "stance" | PhaseName;

export const SEGMENT_ORDER: Segment[] = ["stance", "trophy", "racket_drop", "contact"];

export const SEGMENT_LABELS: Record<Segment, string> = {
  stance: "Stance",
  trophy: "Trophy",
  racket_drop: "Racket drop",
  contact: "Contact / follow-through",
};

export const PHASE_LABELS: Record<PhaseName, string> = {
  trophy: "Trophy",
  racket_drop: "Racket drop",
  contact: "Contact",
};

/** The segment a frame is in: the latest phase event at or before it. */
export function segmentAt(frame: number, phases: PhaseFrames): Segment {
  let current: Segment = "stance";
  let latest = -1;
  for (const name of ["trophy", "racket_drop", "contact"] as const) {
    const start = phases[name];
    if (start !== null && start <= frame && start >= latest) {
      current = name;
      latest = start;
    }
  }
  return current;
}

/** Metrics are assessed at phase events; stance has none. */
export function phaseForSegment(segment: Segment): PhaseName | null {
  return segment === "stance" ? null : segment;
}

import type { AnalysisResult, MetricName, PhaseName } from "../api/types";

/** Advanced mode's numbers for one measurement (computed by serve_analyzer/confidence.py). */
export interface Uncertainty {
  /** 0-1: MediaPipe's confidence in the weakest joint the measurement uses. */
  visibility: number | null;
  level: "high" | "medium" | "low" | null;
  /** Frame-to-frame tracking jitter. */
  noise: number | null;
  /** The camera rig's 90th-percentile error for the camera position. */
  cameraError: number | null;
  /** True when nobody said where the camera was, so side-on (hitting side) was assumed. */
  assumed: boolean;
  /** Half the width of the likely range: camera error plus tracking noise. */
  margin: number | null;
}

export function confidenceLevel(visibility: number | null): Uncertainty["level"] {
  if (visibility === null) return null;
  return visibility >= 0.8 ? "high" : visibility >= 0.5 ? "medium" : "low";
}

export function uncertaintyFor(result: AnalysisResult, phase: PhaseName, metric: MetricName): Uncertainty | null {
  const c = result.confidence?.[phase]?.[metric];
  if (!c) return null;
  const visibility = c.visibility ?? null;
  const noise = c.noise ?? null;
  const cameraError = c.camera_error ?? null;
  const parts = [noise, cameraError].filter((x): x is number => x !== null);
  return {
    visibility,
    level: confidenceLevel(visibility),
    noise,
    cameraError,
    assumed: c.camera_view_assumed ?? false,
    margin: parts.length ? parts.reduce((a, b) => a + b, 0) : null,
  };
}

/** The value plus or minus its margin; null when either is missing. Angles can't go below 0. */
export function likelyRange(value: number | null, u: Uncertainty | null): [number, number] | null {
  if (value === null || !u || u.margin === null) return null;
  return [Math.max(0, value - u.margin), value + u.margin];
}

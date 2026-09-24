import type { AnalysisResult, FramesPayload, MetricName, MetricStatus, PhaseName } from "../api/types";
import { timelineSegments } from "./timeline";

export interface ChartSeries {
  metric: MetricName;
  label: string;
  /** Dash pattern distinguishes series without relying on colour. */
  dash?: number[];
}

export interface ChartSpec {
  id: string;
  title: string;
  unit: "°" | "×";
  /** Plain-English reading of the axis, for the caption. */
  description: string;
  series: ChartSeries[];
  /** Metric whose reference range is drawn as the band. */
  bandMetric: MetricName;
}

export const CHARTS: ChartSpec[] = [
  {
    id: "knee",
    title: "Knee flexion",
    unit: "°",
    description: "0° is a straight leg; higher means more bend.",
    series: [
      { metric: "front_knee_flexion", label: "Front knee" },
      { metric: "back_knee_flexion", label: "Back knee", dash: [6, 4] },
    ],
    bandMetric: "front_knee_flexion",
  },
  {
    id: "elbow",
    title: "Hitting elbow angle",
    unit: "°",
    description: "180° is a straight arm.",
    series: [{ metric: "elbow_angle", label: "Elbow" }],
    bandMetric: "elbow_angle",
  },
  {
    id: "trunk",
    title: "Trunk tilt",
    unit: "°",
    description: "Lean of the torso away from vertical.",
    series: [{ metric: "trunk_tilt", label: "Trunk" }],
    bandMetric: "trunk_tilt",
  },
  {
    id: "wrist",
    title: "Wrist height",
    unit: "×",
    description: "Hitting wrist height in body heights; 1.0 is nose height.",
    series: [{ metric: "wrist_height", label: "Wrist" }],
    bandMetric: "wrist_height",
  },
];

export function formatMetric(metric: MetricName, value: number | null | undefined): string {
  if (value == null) return "—";
  return metric === "wrist_height" ? `${value.toFixed(2)}×` : `${Math.round(value)}°`;
}

export interface Band {
  phase: PhaseName;
  startFrame: number;
  endFrame: number;
  lo: number;
  hi: number;
}

/** The "good" range for each phase segment, drawn only where that phase has one. */
export function referenceBands(
  spec: ChartSpec,
  ranges: AnalysisResult["ranges"],
  phases: AnalysisResult["phases"],
  nFrames: number,
): Band[] {
  return timelineSegments(phases, nFrames).flatMap((segment) => {
    if (segment.segment === "stance") return [];
    const range = ranges[segment.segment][spec.bandMetric];
    if (!range) return [];
    const [lo, hi] = range.good;
    return [{ phase: segment.segment, startFrame: segment.start, endFrame: segment.end, lo, hi }];
  });
}

/** Y range that fits the data and the bands, with a little headroom. */
export function yRange(columns: (number | null)[][], bands: Band[]): [number, number] {
  const values = columns.slice(1).flat().filter((v): v is number => v !== null);
  for (const b of bands) values.push(b.lo, b.hi);
  if (values.length === 0) return [0, 1];
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const pad = (max - min) * 0.08;
  return [min - pad, max + pad];
}

export interface PhasePoint {
  phase: PhaseName;
  metric: MetricName;
  frame: number;
  value: number;
  status: Exclude<MetricStatus, "unknown">;
}

/** The assessed value at each phase event, for status markers on the line. */
export function phasePoints(spec: ChartSpec, result: AnalysisResult): PhasePoint[] {
  const out: PhasePoint[] = [];
  for (const phase of ["trophy", "racket_drop", "contact"] as const) {
    const frame = result.phases[phase];
    if (frame === null) continue;
    for (const { metric } of spec.series) {
      const value = result.metrics[phase][metric];
      const status = result.labels[phase][metric];
      if (value == null || !status || status === "unknown") continue;
      out.push({ phase, metric, frame, value, status });
    }
  }
  return out;
}

/** Min–max text summary for screen readers. */
export function seriesSummary(frames: FramesPayload, series: ChartSeries): string {
  const values = frames.series[series.metric].filter((v): v is number => v != null);
  if (values.length === 0) return `${series.label}: not measured.`;
  const min = Math.min(...values);
  const max = Math.max(...values);
  return `${series.label} ranges from ${formatMetric(series.metric, min)} to ${formatMetric(series.metric, max)}, measured in ${values.length} of ${frames.n_frames} frames.`;
}

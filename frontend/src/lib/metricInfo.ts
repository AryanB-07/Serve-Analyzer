import type { AnalysisResult, MetricName, MetricRange, MetricStatus, PhaseName } from "../api/types";

export interface MetricInfo {
  title: string;
  /** The phase where this metric matters most; its card shows the value there. */
  keyPhase: PhaseName;
  explanation: string;
}

export const METRIC_INFO: Record<MetricName, MetricInfo> = {
  front_knee_flexion: {
    title: "Front knee bend",
    keyPhase: "trophy",
    explanation:
      "How much your front knee bends as you load in the trophy position. A deeper bend stores energy you release by driving up into the ball.",
  },
  back_knee_flexion: {
    title: "Back knee bend",
    keyPhase: "trophy",
    explanation:
      "Bend in your back leg at the trophy position. Loading both legs gives a stronger, more balanced push upward.",
  },
  trunk_tilt: {
    title: "Trunk tilt",
    keyPhase: "trophy",
    explanation:
      "How far your torso leans from vertical at the trophy. A moderate tilt, tossing shoulder high, lets you rotate up and into the ball.",
  },
  elbow_angle: {
    title: "Arm extension",
    keyPhase: "contact",
    explanation:
      "How straight your hitting arm is when you strike the ball. Close to 180° means you are hitting at full reach.",
  },
  wrist_height: {
    title: "Contact height",
    keyPhase: "contact",
    explanation:
      "How high you hit the ball relative to your height (1.0 is nose height). Higher contact gives a better angle down into the service box.",
  },
};

/** Card order: the loading phase first, then contact. */
export const CARD_ORDER: MetricName[] = [
  "front_knee_flexion",
  "back_knee_flexion",
  "trunk_tilt",
  "elbow_angle",
  "wrist_height",
];

export interface MetricReading {
  metric: MetricName;
  phase: PhaseName;
  frame: number | null;
  value: number | null;
  status: MetricStatus;
  range: MetricRange | null;
  direction: "low" | "high" | null;
}

export function directionFor(value: number | null, range: MetricRange | null): "low" | "high" | null {
  if (value === null || !range) return null;
  const [lo, hi] = range.good;
  if (value < lo) return "low";
  if (value > hi) return "high";
  return null;
}

/** Everything a metric card shows, read from the result at the metric's key phase. */
export function readingFor(metric: MetricName, result: AnalysisResult): MetricReading {
  const phase = METRIC_INFO[metric].keyPhase;
  const frame = result.phases[phase];
  const value = frame === null ? null : (result.metrics[phase][metric] ?? null);
  const range = result.ranges[phase][metric] ?? null;
  const status = value === null ? "unknown" : (result.labels[phase][metric] ?? "unknown");
  return { metric, phase, frame, value, status, range, direction: directionFor(value, range) };
}

export interface RangeBarLayout {
  /** [left, width] in percent of the bar. */
  borderline: [number, number];
  good: [number, number];
  /** Value position in percent, or null if not measured. */
  marker: number | null;
  domain: [number, number];
}

/** Positions for the bullet-style range bar; the domain always contains the value. */
export function rangeBarLayout(value: number | null, range: MetricRange): RangeBarLayout {
  let min = range.borderline[0];
  let max = range.borderline[1];
  if (value !== null) {
    min = Math.min(min, value);
    max = Math.max(max, value);
  }
  const pad = (max - min) * 0.1 || 1;
  const d0 = min - pad;
  const d1 = max + pad;
  const pct = (v: number) => ((v - d0) / (d1 - d0)) * 100;
  const span = ([lo, hi]: [number, number]): [number, number] => [pct(lo), pct(hi) - pct(lo)];
  return {
    borderline: span(range.borderline),
    good: span(range.good),
    marker: value === null ? null : pct(value),
    domain: [d0, d1],
  };
}

export function statusCounts(readings: MetricReading[]): Record<MetricStatus, number> {
  const out: Record<MetricStatus, number> = { good: 0, borderline: 0, off: 0, unknown: 0 };
  for (const r of readings) out[r.status] += 1;
  return out;
}

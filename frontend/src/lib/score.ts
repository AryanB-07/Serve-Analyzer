import type { MetricRange, MetricStatus } from "../api/types";

/**
 * Simple mode's 0-100 scores: where a measurement sits against its reference range.
 *
 *   100 ............ 80 ............ 50 ............ 0
 *   centre of good   edge of good    edge of borderline   one borderline-width beyond
 *
 * So a score is always in the same band as the measurement's label: good 80-100, borderline
 * 50-79, needs work 0-49. The ranges are general guides, not a coach's verdict, which the page says.
 */
export const SCORE_BANDS: { status: Exclude<MetricStatus, "unknown">; from: number; to: number }[] = [
  { status: "off", from: 0, to: 50 },
  { status: "borderline", from: 50, to: 80 },
  { status: "good", from: 80, to: 100 },
];

function statusOf(value: number, range: MetricRange): Exclude<MetricStatus, "unknown"> {
  const [g0, g1] = range.good;
  const [b0, b1] = range.borderline;
  if (value >= g0 && value <= g1) return "good";
  if (value >= b0 && value <= b1) return "borderline";
  return "off";
}

function raw(value: number, range: MetricRange): number {
  const [g0, g1] = range.good;
  const [b0, b1] = range.borderline;
  if (value >= g0 && value <= g1) {
    const half = (g1 - g0) / 2;
    return half > 0 ? 80 + 20 * (1 - Math.abs(value - (g0 + g1) / 2) / half) : 100;
  }
  const below = value < g0;
  const edge = below ? g0 : g1;
  const band = below ? g0 - b0 : b1 - g1; // the borderline band on this side (may be empty)
  const distance = Math.abs(value - edge);
  if (band > 0 && distance <= band) return 80 - (30 * distance) / band;
  const scale = band > 0 ? band : Math.max(1e-9, g1 - g0);
  const beyond = band > 0 ? distance - band : distance;
  return Math.max(0, 50 - (50 * beyond) / scale);
}

/** 0-100, or null when there's nothing to score. */
export function scoreFor(value: number | null, range: MetricRange | null): number | null {
  if (value === null || !range) return null;
  const band = SCORE_BANDS.find((b) => b.status === statusOf(value, range))!;
  const top = band.status === "good" ? 100 : band.to - 1;
  return Math.min(top, Math.max(band.from, Math.round(raw(value, range))));
}

/** The status band a score falls in. */
export function bandOf(score: number): Exclude<MetricStatus, "unknown"> {
  return score >= 80 ? "good" : score >= 50 ? "borderline" : "off";
}

/** The average of the scores there are, or null when there are none. */
export function overallScore(scores: (number | null)[]): number | null {
  const present = scores.filter((s): s is number => s !== null);
  return present.length ? Math.round(present.reduce((a, b) => a + b, 0) / present.length) : null;
}

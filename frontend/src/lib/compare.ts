import type { AnalysisSummary, MetricRange } from "../api/types";

export type Change = "better" | "worse" | "same" | "n/a";

/** How far a value is outside the good range (0 when inside). */
export function distanceToRange(value: number, range: MetricRange): number {
  const [lo, hi] = range.good;
  return value < lo ? lo - value : value > hi ? value - hi : 0;
}

/**
 * Whether B is closer to the good range than A. "Better" is about the
 * reference range, not the raw number going up or down. Changes smaller than
 * 5% of the range width count as the same: below that they are measurement
 * noise and often invisible at display precision.
 */
export function compareMetric(a: number | null, b: number | null, range: MetricRange | null): Change {
  if (a === null || b === null || !range) return "n/a";
  const tolerance = (range.good[1] - range.good[0]) * 0.05;
  const da = distanceToRange(a, range);
  const db = distanceToRange(b, range);
  if (Math.abs(da - db) <= tolerance) return "same";
  return db < da ? "better" : "worse";
}

/** Add or remove an id, keeping at most `max` selected (oldest selection dropped). */
export function toggleSelection(selected: string[], id: string, max = 2): string[] {
  if (selected.includes(id)) return selected.filter((s) => s !== id);
  return [...selected, id].slice(-max);
}

/** Compare older ("before") against newer ("after"). */
export function beforeAfter<T extends Pick<AnalysisSummary, "created_at">>(x: T, y: T): [T, T] {
  return Date.parse(x.created_at) <= Date.parse(y.created_at) ? [x, y] : [y, x];
}

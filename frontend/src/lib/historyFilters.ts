import type { components } from "../api/schema";

export type KeyPosition = NonNullable<components["schemas"]["KeyScores"]> extends infer K ? keyof K & string : never;
export type ScoreBand = "good" | "borderline" | "off";

/**
 * History's sidebar filters. They live in the URL (?time=30d&score=good&stat=trunk_tilt&band=off),
 * so Back, reloads and shared links keep them.
 */
export interface HistoryFilters {
  time: "all" | "7d" | "30d" | "90d" | "custom";
  from: string | null; // YYYY-MM-DD, for "custom"
  to: string | null;
  score: "any" | ScoreBand;
  stat: KeyPosition | null;
  band: ScoreBand | null;
}

export const DEFAULT_FILTERS: HistoryFilters = { time: "all", from: null, to: null, score: "any", stat: null, band: null };

export const KEY_POSITIONS: KeyPosition[] = ["front_knee_flexion", "back_knee_flexion", "trunk_tilt", "elbow_angle", "wrist_height"];
const TIMES = ["all", "7d", "30d", "90d", "custom"] as const;
const BANDS = ["good", "borderline", "off"] as const;
const DATE = /^\d{4}-\d{2}-\d{2}$/;

export function parseFilters(params: URLSearchParams): HistoryFilters {
  const pick = <T extends string>(value: string | null, allowed: readonly T[], fallback: T) =>
    (allowed as readonly string[]).includes(value ?? "") ? (value as T) : fallback;
  const stat = params.get("stat");
  const band = params.get("band");
  const validStat = (KEY_POSITIONS as string[]).includes(stat ?? "") ? (stat as KeyPosition) : null;
  const validBand = (BANDS as readonly string[]).includes(band ?? "") ? (band as ScoreBand) : null;
  return {
    time: pick(params.get("time"), TIMES, "all"),
    from: DATE.test(params.get("from") ?? "") ? params.get("from") : null,
    to: DATE.test(params.get("to") ?? "") ? params.get("to") : null,
    score: pick(params.get("score"), ["any", ...BANDS] as const, "any"),
    // A stat filter needs both halves.
    stat: validStat && validBand ? validStat : null,
    band: validStat && validBand ? validBand : null,
  };
}

/** Only the filters that differ from the defaults, so a plain History URL stays plain. */
export function filtersToParams(f: HistoryFilters): URLSearchParams {
  const p = new URLSearchParams();
  if (f.time !== "all") p.set("time", f.time);
  if (f.time === "custom" && f.from) p.set("from", f.from);
  if (f.time === "custom" && f.to) p.set("to", f.to);
  if (f.score !== "any") p.set("score", f.score);
  if (f.stat && f.band) {
    p.set("stat", f.stat);
    p.set("band", f.band);
  }
  return p;
}

export function isFiltered(f: HistoryFilters): boolean {
  return filtersToParams(f).size > 0;
}

const SCORE_RANGES: Record<ScoreBand, [number, number]> = { good: [80, 100], borderline: [50, 79], off: [0, 49] };

/** The API's query parameters (GET /analyses). ``today`` is injectable for tests. */
export function apiQuery(f: HistoryFilters, today: Date = new Date()): Record<string, string> {
  const q: Record<string, string> = {};
  if (f.time === "7d" || f.time === "30d" || f.time === "90d") {
    const days = Number(f.time.slice(0, -1));
    q.uploaded_from = new Date(today.getTime() - days * 86_400_000).toISOString();
  } else if (f.time === "custom") {
    // Local midnight at the start of "from", and the end of "to" (the API's upper bound is exclusive).
    if (f.from) q.uploaded_from = new Date(`${f.from}T00:00:00`).toISOString();
    if (f.to) q.uploaded_to = new Date(new Date(`${f.to}T00:00:00`).getTime() + 86_400_000).toISOString();
  }
  if (f.score !== "any") {
    const [lo, hi] = SCORE_RANGES[f.score];
    q.min_score = String(lo);
    q.max_score = String(hi);
  }
  if (f.stat && f.band) {
    q.stat = f.stat;
    q.stat_band = f.band;
  }
  return q;
}

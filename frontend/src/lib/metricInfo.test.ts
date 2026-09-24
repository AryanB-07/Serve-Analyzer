import { describe, expect, it } from "vitest";

import type { AnalysisResult } from "../api/types";
import { CARD_ORDER, directionFor, rangeBarLayout, readingFor, statusCounts } from "./metricInfo";

const result = {
  phases: { trophy: 113, racket_drop: null, contact: 124 },
  metrics: {
    trophy: { front_knee_flexion: 86.2, back_knee_flexion: null, elbow_angle: null, trunk_tilt: 20.2, wrist_height: null },
    racket_drop: { front_knee_flexion: null, back_knee_flexion: null, elbow_angle: null, trunk_tilt: null, wrist_height: null },
    contact: { front_knee_flexion: 4, back_knee_flexion: null, elbow_angle: null, trunk_tilt: 20, wrist_height: 1.287 },
  },
  labels: {
    trophy: { front_knee_flexion: "borderline", back_knee_flexion: "unknown", trunk_tilt: "good" },
    racket_drop: {},
    contact: { wrist_height: "borderline", elbow_angle: "unknown" },
  },
  ranges: {
    trophy: {
      front_knee_flexion: { good: [50, 80], borderline: [35, 95] },
      back_knee_flexion: { good: [45, 80], borderline: [30, 95] },
      trunk_tilt: { good: [15, 35], borderline: [8, 45] },
    },
    racket_drop: {},
    contact: {
      elbow_angle: { good: [160, 180], borderline: [145, 180] },
      wrist_height: { good: [1.3, 1.6], borderline: [1.15, 1.7] },
    },
  },
} as unknown as AnalysisResult;

describe("readingFor", () => {
  it("reads each metric at its key phase", () => {
    expect(readingFor("front_knee_flexion", result)).toEqual({
      metric: "front_knee_flexion", phase: "trophy", frame: 113, value: 86.2, status: "borderline",
      range: { good: [50, 80], borderline: [35, 95] }, direction: "high",
    });
    expect(readingFor("wrist_height", result)).toMatchObject({ phase: "contact", value: 1.287, direction: "low" });
  });

  it("reports unmeasured metrics as unknown", () => {
    expect(readingFor("elbow_angle", result)).toMatchObject({ value: null, status: "unknown", direction: null });
  });

  it("treats a missing key phase as not measured", () => {
    const noTrophy = { ...result, phases: { ...result.phases, trophy: null } } as AnalysisResult;
    expect(readingFor("trunk_tilt", noTrophy)).toMatchObject({ frame: null, value: null, status: "unknown" });
  });

  it("covers every metric", () => {
    expect(CARD_ORDER.map((m) => readingFor(m, result).metric)).toHaveLength(5);
  });
});

describe("directionFor", () => {
  const range = { good: [10, 20] as [number, number], borderline: [5, 30] as [number, number] };
  it("says which side of the good range a value is on", () => {
    expect(directionFor(5, range)).toBe("low");
    expect(directionFor(15, range)).toBeNull();
    expect(directionFor(25, range)).toBe("high");
    expect(directionFor(null, range)).toBeNull();
  });
});

describe("rangeBarLayout", () => {
  it("nests the good range inside the borderline range", () => {
    const layout = rangeBarLayout(86, { good: [50, 80], borderline: [35, 95] });
    const [bl, bw] = layout.borderline;
    const [gl, gw] = layout.good;
    expect(gl).toBeGreaterThan(bl);
    expect(gl + gw).toBeLessThan(bl + bw);
    expect(layout.marker).toBeGreaterThan(gl + gw);
  });

  it("extends the domain to fit an out-of-range value", () => {
    const layout = rangeBarLayout(200, { good: [160, 180], borderline: [145, 180] });
    expect(layout.marker).toBeLessThan(100);
    expect(layout.domain[1]).toBeGreaterThan(200);
  });

  it("has no marker when unmeasured", () => {
    expect(rangeBarLayout(null, { good: [1, 2], borderline: [0, 3] }).marker).toBeNull();
  });
});

describe("statusCounts", () => {
  it("tallies statuses", () => {
    const counts = statusCounts(CARD_ORDER.map((m) => readingFor(m, result)));
    expect(counts).toEqual({ good: 1, borderline: 2, off: 0, unknown: 2 });
  });
});

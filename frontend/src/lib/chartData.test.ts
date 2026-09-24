import { describe, expect, it } from "vitest";

import type { AnalysisResult, FramesPayload } from "../api/types";
import { CHARTS, formatMetric, phasePoints, referenceBands, seriesSummary, yRange } from "./chartData";

const elbow = CHARTS.find((c) => c.id === "elbow")!;
const knee = CHARTS.find((c) => c.id === "knee")!;

const frames = {
  fps: 25,
  n_frames: 4,
  series: {
    elbow_angle: [150, null, 170, 175],
    front_knee_flexion: [10, 20, null, 30],
    back_knee_flexion: [null, null, null, null],
    trunk_tilt: [0, 0, 0, 0],
    wrist_height: [1, 1, 1, 1],
  },
} as unknown as FramesPayload;

const result = {
  phases: { trophy: 1, racket_drop: null, contact: 3 },
  ranges: {
    trophy: { elbow_angle: { good: [80, 120], borderline: [65, 140] } },
    racket_drop: { elbow_angle: { good: [50, 90], borderline: [35, 110] } },
    contact: { elbow_angle: { good: [160, 180], borderline: [145, 180] } },
  },
  metrics: {
    trophy: { elbow_angle: null, front_knee_flexion: 20, back_knee_flexion: null },
    racket_drop: {},
    contact: { elbow_angle: 175, front_knee_flexion: 30, back_knee_flexion: null },
  },
  labels: {
    trophy: { elbow_angle: "unknown", front_knee_flexion: "off" },
    racket_drop: {},
    contact: { elbow_angle: "good", front_knee_flexion: "borderline" },
  },
} as unknown as AnalysisResult;

describe("referenceBands", () => {
  it("draws each phase's own range over that phase's segment, skipping undetected phases", () => {
    expect(referenceBands(elbow, result.ranges, result.phases, 4)).toEqual([
      { phase: "trophy", startFrame: 1, endFrame: 3, lo: 80, hi: 120 },
      { phase: "contact", startFrame: 3, endFrame: 4, lo: 160, hi: 180 },
    ]);
  });

  it("draws nothing for phases without a range for the metric", () => {
    expect(referenceBands(knee, result.ranges, result.phases, 4)).toEqual([]);
  });
});

describe("yRange", () => {
  it("fits data and bands with headroom", () => {
    const [min, max] = yRange([[0, 1], [150, 170]], [{ phase: "trophy", startFrame: 0, endFrame: 1, lo: 80, hi: 120 }]);
    expect(min).toBeLessThan(80);
    expect(max).toBeGreaterThan(170);
  });

  it("falls back when nothing was measured", () => {
    expect(yRange([[0, 1], [null, null]], [])).toEqual([0, 1]);
  });
});

describe("phasePoints", () => {
  it("returns assessed values at detected phases, skipping unknown", () => {
    expect(phasePoints(elbow, result)).toEqual([
      { phase: "contact", metric: "elbow_angle", frame: 3, value: 175, status: "good" },
    ]);
    expect(phasePoints(knee, result).map((p) => [p.phase, p.status])).toEqual([
      ["trophy", "off"],
      ["contact", "borderline"],
    ]);
  });
});

describe("formatting and summaries", () => {
  it("formats angles and heights", () => {
    expect(formatMetric("elbow_angle", 163.6)).toBe("164°");
    expect(formatMetric("wrist_height", 1.287)).toBe("1.29×");
    expect(formatMetric("trunk_tilt", null)).toBe("—");
  });

  it("summarises range and coverage", () => {
    expect(seriesSummary(frames, elbow.series[0]!)).toBe(
      "Elbow ranges from 150° to 175°, measured in 3 of 4 frames.",
    );
    expect(seriesSummary(frames, knee.series[1]!)).toBe("Back knee: not measured.");
  });
});

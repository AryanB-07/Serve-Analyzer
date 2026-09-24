/** Edge cases for the pure helpers: tiny clips, missing data, odd inputs. */
import { describe, expect, it } from "vitest";

import type { AnalysisResult, FramesPayload } from "../api/types";
import { makeResult } from "../test/fixtures";
import { mapFrame, phaseAnchors, resampleOnto } from "./align";
import { referenceBands, yRange, CHARTS } from "./chartData";
import { beforeAfter, compareMetric, toggleSelection } from "./compare";
import { mediaRect, toPixel } from "./coords";
import { readingFor } from "./metricInfo";
import { segmentAt } from "./phases";
import { createStatusBackoff, isActive } from "./polling";
import { angleLabels, jointStatuses, poseAt } from "./skeleton";
import { clampFrame, frameAtTime, timeForFrame } from "./time";
import { fractionForFrame, frameAtFraction, timelineSegments } from "./timeline";

describe("time on degenerate clips", () => {
  it("never produces NaN frames", () => {
    expect(clampFrame(NaN, 10)).toBe(0);
    expect(frameAtTime(NaN, 25, 10)).toBe(0);
  });

  it("handles a one-frame clip", () => {
    expect(frameAtTime(0, 30, 1)).toBe(0);
    expect(frameAtTime(5, 30, 1)).toBe(0);
    expect(timeForFrame(3, 30, 1)).toBeCloseTo(0.5 / 30);
    expect(frameAtFraction(0.99, 1)).toBe(0);
    expect(fractionForFrame(0, 1)).toBe(0.5);
  });

  it("round-trips at slow-motion frame rates", () => {
    for (let f = 0; f < 3600; f += 7) expect(frameAtTime(timeForFrame(f, 240, 3600), 240, 3600)).toBe(f);
  });
});

describe("timeline and phases with odd detections", () => {
  it("clamps phase frames beyond the clip", () => {
    expect(timelineSegments({ trophy: 5, racket_drop: null, contact: 999 }, 10)).toEqual([
      { segment: "stance", start: 0, end: 5 },
      { segment: "trophy", start: 5, end: 9 },
      { segment: "contact", start: 9, end: 10 },
    ]);
  });

  it("orders segments by frame even if phases arrive out of order", () => {
    expect(segmentAt(8, { trophy: 9, racket_drop: null, contact: 6 })).toBe("contact");
  });
});

describe("coordinates for tiny and extreme sizes", () => {
  it("keeps points off the frame outside the media rect", () => {
    const rect = mediaRect({ width: 100, height: 100 }, { width: 200, height: 100 });
    expect(toPixel({ x: 1.2, y: -0.1 }, rect)).toEqual({ x: 120, y: 20 });
  });
});

describe("alignment edge cases", () => {
  const A = { fps: 30, nFrames: 90, phases: { trophy: 40, racket_drop: 50, contact: 60 } };

  it("is the identity for a clip compared with itself", () => {
    const anchors = phaseAnchors(A, A);
    for (const f of [0, 40, 45, 60, 89]) expect(mapFrame(f, A, A, anchors)).toEqual({ frame: f, outside: false });
  });

  it("flags A frames after B's footage ends", () => {
    const B = { fps: 30, nFrames: 65, phases: { trophy: 40, racket_drop: 50, contact: 60 } };
    const anchors = phaseAnchors(A, B);
    expect(mapFrame(64, A, B, anchors).outside).toBe(false);
    expect(mapFrame(80, A, B, anchors)).toEqual({ frame: 64, outside: true });
  });

  it("falls back to raw time with no shared phases", () => {
    const B = { fps: 30, nFrames: 50, phases: { trophy: null, racket_drop: null, contact: null } };
    const anchors = phaseAnchors(A, B);
    expect(anchors).toEqual([]);
    const out = resampleOnto(Array.from({ length: 50 }, (_, i) => i), A, B, anchors);
    expect(out[10]).toBe(10);
    expect(out[70]).toBeNull();
  });
});

describe("polling", () => {
  it("only polls statuses where work is happening", () => {
    expect(isActive("queued")).toBe(true);
    expect(isActive("rendering")).toBe(true);
    expect(isActive("awaiting_upload")).toBe(false);
    expect(isActive("failed")).toBe(false);
    expect(isActive(undefined)).toBe(false);
  });

  it("stops for an abandoned upload and restarts fast after a retry", () => {
    const next = createStatusBackoff();
    expect(next("awaiting_upload", 0)).toBe(false);
    expect(next("failed", 1)).toBe(false);
    expect(next("queued", 2)).toBe(1000);
  });
});

describe("skeleton with missing data", () => {
  const frames = {
    fps: 25, n_frames: 2, width: 640, height: 480,
    phases: { trophy: null, racket_drop: null, contact: null },
    landmarks: { raw: {}, smoothed: { nose: { x: [0.5, null], y: [0.5, null] } } },
    series: { elbow_angle: [null, null], front_knee_flexion: [null, null], back_knee_flexion: [null, null], trunk_tilt: [null, null], wrist_height: [null, null] },
  } as unknown as FramesPayload;

  it("draws nothing for frames outside the data", () => {
    expect(poseAt(frames, 5, "smoothed")).toEqual({});
    expect(poseAt(frames, 1, "smoothed")).toEqual({});
  });

  it("has no labels when nothing was measured", () => {
    expect(angleLabels(frames, 0, "left", { nose: { x: 0, y: 0 } })).toEqual([]);
  });

  it("shows the worst status on joints shared by two metrics", () => {
    const labels = { trophy: {}, racket_drop: {}, contact: { trunk_tilt: "good", elbow_angle: "off" } } as AnalysisResult["labels"];
    expect(jointStatuses(labels, "contact", "left")).toMatchObject({ left_elbow: "off", left_hip: "good" });
  });
});

describe("charts and metrics with missing phases or ranges", () => {
  it("draws no band for a phase without a range", () => {
    const result = makeResult({ phases: { trophy: null, racket_drop: null, contact: null } });
    const spec = CHARTS.find((c) => c.id === "elbow")!;
    expect(referenceBands(spec, result.ranges, result.phases, 125)).toEqual([]);
  });

  it("gives a flat series some height", () => {
    const [lo, hi] = yRange([[0, 1], [5, 5]], []);
    expect(hi - lo).toBeGreaterThan(0);
  });

  it("reads a metric whose phase has no reference range", () => {
    const result = makeResult();
    const noRanges = { ...result, ranges: { ...result.ranges, contact: {} } } as AnalysisResult;
    expect(readingFor("wrist_height", noRanges)).toMatchObject({ range: null, direction: null, value: 1.287 });
  });
});

describe("compare helpers at the boundaries", () => {
  it("keeps only the latest pick when the limit is one", () => {
    expect(toggleSelection(["a"], "b", 1)).toEqual(["b"]);
  });

  it("keeps the given order for identical timestamps", () => {
    const x = { id: "x", created_at: "2026-09-20T10:00:00Z" };
    const y = { id: "y", created_at: "2026-09-20T10:00:00Z" };
    expect(beforeAfter(x, y).map((s) => s.id)).toEqual(["x", "y"]);
  });

  it("treats a zero-width range sensibly", () => {
    const range = { good: [10, 10] as [number, number], borderline: [5, 15] as [number, number] };
    expect(compareMetric(14, 11, range)).toBe("better");
    expect(compareMetric(10, 10, range)).toBe("same");
  });
});

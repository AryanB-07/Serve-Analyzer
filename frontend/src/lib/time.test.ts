import { describe, expect, it } from "vitest";

import { clampFrame, frameAtTime, timeForFrame } from "./time";

describe("frame/time conversion", () => {
  it("absorbs floating-point error at exact frame times", () => {
    expect(1.16 * 25).toBeLessThan(29); // 28.999999999999996
    expect(frameAtTime(1.16, 25, 125)).toBe(29);
    for (let f = 0; f < 400; f++) expect(frameAtTime(f / 25, 25, 400)).toBe(f);
  });

  it("round-trips every frame through its seek time", () => {
    for (const fps of [24, 25, 29.97, 30, 60, 240]) {
      for (let f = 0; f < 50; f++) expect(frameAtTime(timeForFrame(f, fps, 50), fps, 50)).toBe(f);
    }
  });

  it("clamps to the clip", () => {
    expect(frameAtTime(-1, 30, 10)).toBe(0);
    expect(frameAtTime(99, 30, 10)).toBe(9);
    expect(timeForFrame(99, 10, 10)).toBeCloseTo(0.95);
    expect(clampFrame(3.7, 10)).toBe(3);
    expect(clampFrame(5, 0)).toBe(0);
  });
});

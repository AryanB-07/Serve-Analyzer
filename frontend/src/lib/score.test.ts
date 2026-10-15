import { describe, expect, it } from "vitest";

// The demo's ranges are the reference ranges (tests/test_mock_fixtures.py checks they match).
import demo from "../../public/mock/demo-serve-1/result.json";
import type { MetricRange } from "../api/types";
import { bandOf, overallScore, scoreFor } from "./score";

const KNEE: MetricRange = { good: [50, 80], borderline: [35, 95] };
const ELBOW_AT_CONTACT: MetricRange = { good: [160, 180], borderline: [145, 180] };

function serverLabel(value: number, range: MetricRange) {
  const [g0, g1] = range.good;
  const [b0, b1] = range.borderline;
  return value >= g0 && value <= g1 ? "good" : value >= b0 && value <= b1 ? "borderline" : "off";
}

describe("scores", () => {
  it("are 100 at the centre of the good range and 80 at its edges", () => {
    expect(scoreFor(65, KNEE)).toBe(100);
    expect(scoreFor(50, KNEE)).toBe(80);
    expect(scoreFor(80, KNEE)).toBe(80);
  });

  it("fall from 79 to 50 across the borderline band, then to 0", () => {
    expect(scoreFor(42.5, KNEE)).toBe(65);
    expect(scoreFor(35, KNEE)).toBe(50);
    expect(scoreFor(28, KNEE)).toBeLessThan(50);
    expect(scoreFor(20, KNEE)).toBe(0);
    expect(scoreFor(-100, KNEE)).toBe(0);
  });

  it("handle a range with no borderline band on one side", () => {
    expect(scoreFor(180, ELBOW_AT_CONTACT)).toBe(80);
    expect(scoreFor(170, ELBOW_AT_CONTACT)).toBe(100);
    expect(scoreFor(150, ELBOW_AT_CONTACT)).toBeGreaterThanOrEqual(50);
  });

  it("are null with nothing to score", () => {
    expect(scoreFor(null, KNEE)).toBeNull();
    expect(scoreFor(60, null)).toBeNull();
  });

  it("always fall in the same band as the measurement's label, for every reference range", () => {
    for (const [phase, metrics] of Object.entries(demo.ranges)) {
      for (const range of Object.values(metrics as unknown as Record<string, MetricRange | null>)) {
        if (!range) continue;
        const [b0, b1] = range.borderline;
        const span = b1 - b0;
        for (let i = -40; i <= 140; i++) {
          const value = b0 + (span * i) / 100;
          const score = scoreFor(value, range)!;
          expect(bandOf(score), `${phase} ${value}`).toBe(serverLabel(value, range));
          expect(score).toBeGreaterThanOrEqual(0);
          expect(score).toBeLessThanOrEqual(100);
        }
      }
    }
  });

  it("never get better as a value moves further from the good range", () => {
    let last = 100;
    for (let v = 65; v >= 0; v -= 0.5) {
      const s = scoreFor(v, KNEE)!;
      expect(s).toBeLessThanOrEqual(last);
      last = s;
    }
  });

  it("average into an overall score, ignoring what wasn't scored", () => {
    expect(overallScore([100, 80, null, 60])).toBe(80);
    expect(overallScore([null, null])).toBeNull();
  });
});

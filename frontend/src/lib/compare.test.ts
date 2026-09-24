import { describe, expect, it } from "vitest";

import { beforeAfter, compareMetric, distanceToRange, toggleSelection } from "./compare";

const range = { good: [50, 80] as [number, number], borderline: [35, 95] as [number, number] };

describe("compareMetric", () => {
  it("measures improvement as getting closer to the good range", () => {
    expect(distanceToRange(86, range)).toBe(6);
    expect(distanceToRange(60, range)).toBe(0);
    expect(compareMetric(86, 78, range)).toBe("better");
    expect(compareMetric(40, 30, range)).toBe("worse");
    expect(compareMetric(90, 45, range)).toBe("better");
  });

  it("treats movement inside the range, or tiny changes, as the same", () => {
    expect(compareMetric(55, 75, range)).toBe("same");
    expect(compareMetric(86, 85.6, range)).toBe("same");
    // Both display as 1.29x; calling that an improvement would look broken.
    const wrist = { good: [1.3, 1.6] as [number, number], borderline: [1.15, 1.7] as [number, number] };
    expect(compareMetric(1.287, 1.294, wrist)).toBe("same");
    expect(compareMetric(1.2, 1.28, wrist)).toBe("better");
  });

  it("is n/a without both values and a range", () => {
    expect(compareMetric(null, 60, range)).toBe("n/a");
    expect(compareMetric(60, 70, null)).toBe("n/a");
  });
});

describe("selection helpers", () => {
  it("toggles and keeps at most two", () => {
    expect(toggleSelection([], "a")).toEqual(["a"]);
    expect(toggleSelection(["a"], "b")).toEqual(["a", "b"]);
    expect(toggleSelection(["a", "b"], "c")).toEqual(["b", "c"]);
    expect(toggleSelection(["a", "b"], "a")).toEqual(["b"]);
  });

  it("orders before/after by date", () => {
    const older = { id: "1", created_at: "2026-09-13T10:00:00Z" };
    const newer = { id: "2", created_at: "2026-09-20T10:00:00Z" };
    expect(beforeAfter(newer, older).map((x) => x.id)).toEqual(["1", "2"]);
  });
});

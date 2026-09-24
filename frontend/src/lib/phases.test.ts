import { describe, expect, it } from "vitest";

import { phaseForSegment, segmentAt } from "./phases";

describe("segmentAt", () => {
  const phases = { trophy: 10, racket_drop: 20, contact: 30 };

  it("walks through the segments in order", () => {
    expect([0, 9, 10, 19, 20, 29, 30, 99].map((f) => segmentAt(f, phases))).toEqual([
      "stance", "stance", "trophy", "trophy", "racket_drop", "racket_drop", "contact", "contact",
    ]);
  });

  it("skips undetected phases", () => {
    const partial = { trophy: 10, racket_drop: null, contact: 30 };
    expect(segmentAt(25, partial)).toBe("trophy");
    expect(segmentAt(5, { trophy: null, racket_drop: null, contact: null })).toBe("stance");
  });
});

describe("phaseForSegment", () => {
  it("has no phase for stance", () => {
    expect(phaseForSegment("stance")).toBeNull();
    expect(phaseForSegment("contact")).toBe("contact");
  });
});

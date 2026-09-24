import { describe, expect, it } from "vitest";

import { fractionForFrame, frameAtFraction, phaseMarkers, timelineSegments } from "./timeline";

describe("timelineSegments", () => {
  it("covers the whole clip with contiguous segments", () => {
    expect(timelineSegments({ trophy: 40, racket_drop: 60, contact: 70 }, 100)).toEqual([
      { segment: "stance", start: 0, end: 40 },
      { segment: "trophy", start: 40, end: 60 },
      { segment: "racket_drop", start: 60, end: 70 },
      { segment: "contact", start: 70, end: 100 },
    ]);
  });

  it("skips undetected phases so the previous segment runs on", () => {
    expect(timelineSegments({ trophy: 113, racket_drop: null, contact: 124 }, 125)).toEqual([
      { segment: "stance", start: 0, end: 113 },
      { segment: "trophy", start: 113, end: 124 },
      { segment: "contact", start: 124, end: 125 },
    ]);
  });

  it("drops zero-length segments and handles no phases", () => {
    expect(timelineSegments({ trophy: 0, racket_drop: null, contact: null }, 10)).toEqual([
      { segment: "trophy", start: 0, end: 10 },
    ]);
    expect(timelineSegments({ trophy: null, racket_drop: null, contact: null }, 10)).toEqual([
      { segment: "stance", start: 0, end: 10 },
    ]);
  });
});

describe("phaseMarkers", () => {
  it("lists detected phases in frame order", () => {
    expect(phaseMarkers({ trophy: 40, racket_drop: null, contact: 70 })).toEqual([
      { phase: "trophy", frame: 40 },
      { phase: "contact", frame: 70 },
    ]);
  });
});

describe("position <-> frame", () => {
  it("maps track positions to frames and back to slot centres", () => {
    expect(frameAtFraction(0, 125)).toBe(0);
    expect(frameAtFraction(0.5, 125)).toBe(62);
    expect(frameAtFraction(1, 125)).toBe(124);
    expect(frameAtFraction(-0.2, 125)).toBe(0);
    expect(fractionForFrame(0, 4)).toBe(0.125);
    for (let f = 0; f < 125; f++) expect(frameAtFraction(fractionForFrame(f, 125), 125)).toBe(f);
  });
});

import { describe, expect, it } from "vitest";

import { mapFrame, mapTime, phaseAnchors, resampleOnto, slopeAt, type ClipTiming } from "./align";

// The two demo clips: B is A with its first 20 frames cut off.
const A: ClipTiming = { fps: 25, nFrames: 125, phases: { trophy: 113, racket_drop: null, contact: 124 } };
const B: ClipTiming = { fps: 25, nFrames: 105, phases: { trophy: 92, racket_drop: null, contact: 104 } };

describe("phaseAnchors", () => {
  it("pairs phases detected in both clips", () => {
    expect(phaseAnchors(A, B)).toEqual([
      { phase: "trophy", a: 4.52, b: 3.68 },
      { phase: "contact", a: 4.96, b: 4.16 },
    ]);
  });

  it("skips phases missing from either clip", () => {
    const noTrophy = { ...B, phases: { ...B.phases, trophy: null } };
    expect(phaseAnchors(A, noTrophy)).toEqual([{ phase: "contact", a: 4.96, b: 4.16 }]);
  });

  it("drops pairs that would run time backwards", () => {
    const swapped = { ...B, phases: { trophy: 50, racket_drop: 40, contact: 60 } };
    const a = { ...A, phases: { trophy: 10, racket_drop: 20, contact: 30 } };
    expect(phaseAnchors(a, swapped).map((x) => x.b)).toEqual([2, 2.4]);
  });

  it("handles different frame rates", () => {
    const slowmo = { fps: 60, nFrames: 600, phases: { trophy: 300, racket_drop: null, contact: 330 } };
    expect(phaseAnchors(A, slowmo)).toEqual([
      { phase: "trophy", a: 4.52, b: 5 },
      { phase: "contact", a: 4.96, b: 5.5 },
    ]);
  });
});

describe("mapTime and slopeAt", () => {
  const anchors = [
    { a: 2, b: 1 },
    { a: 3, b: 3 },
  ];

  it("hits anchors exactly and interpolates between them", () => {
    expect(mapTime(2, anchors)).toBe(1);
    expect(mapTime(3, anchors)).toBe(3);
    expect(mapTime(2.5, anchors)).toBe(2);
    expect(slopeAt(2.5, anchors)).toBe(2);
  });

  it("runs in real time outside the anchors", () => {
    expect(mapTime(0, anchors)).toBe(-1);
    expect(mapTime(4, anchors)).toBe(4);
    expect(slopeAt(0.5, anchors)).toBe(1);
    expect(slopeAt(3.5, anchors)).toBe(1);
  });

  it("is the identity with no anchors", () => {
    expect(mapTime(1.23, [])).toBe(1.23);
    expect(slopeAt(1.23, [])).toBe(1);
  });
});

describe("mapFrame", () => {
  const anchors = phaseAnchors(A, B);

  it("lines up the phase frames exactly", () => {
    expect(mapFrame(113, A, B, anchors)).toEqual({ frame: 92, outside: false });
    expect(mapFrame(124, A, B, anchors)).toEqual({ frame: 104, outside: false });
  });

  it("flags A moments that B never shows, clamped to B's first frame", () => {
    expect(mapFrame(0, A, B, anchors)).toEqual({ frame: 0, outside: true });
    expect(mapFrame(50, A, B, anchors).outside).toBe(false);
  });
});

describe("resampleOnto", () => {
  it("re-indexes B's series onto A's frames with gaps where B has no footage", () => {
    const anchors = phaseAnchors(A, B);
    const seriesB = Array.from({ length: B.nFrames }, (_, i) => i);
    const out = resampleOnto(seriesB, A, B, anchors);
    expect(out).toHaveLength(A.nFrames);
    expect(out[113]).toBe(92);
    expect(out[124]).toBe(104);
    expect(out[0]).toBeNull();
  });
});

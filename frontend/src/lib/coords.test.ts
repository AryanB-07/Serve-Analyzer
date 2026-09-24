import { describe, expect, it } from "vitest";

import { canvasBackingSize, mediaRect, toPixel } from "./coords";

describe("mediaRect", () => {
  it("letterboxes a landscape video in a taller box (bars top and bottom)", () => {
    expect(mediaRect({ width: 800, height: 800 }, { width: 1920, height: 1080 })).toEqual({
      x: 0, y: 175, width: 800, height: 450,
    });
  });

  it("pillarboxes a portrait video in a wide box (bars left and right)", () => {
    expect(mediaRect({ width: 1000, height: 640 }, { width: 1080, height: 1920 })).toEqual({
      x: 320, y: 0, width: 360, height: 640,
    });
  });

  it("fills exactly when aspect ratios match", () => {
    expect(mediaRect({ width: 640, height: 480 }, { width: 320, height: 240 })).toEqual({
      x: 0, y: 0, width: 640, height: 480,
    });
  });

  it("crops with cover and stretches with fill", () => {
    expect(mediaRect({ width: 800, height: 800 }, { width: 1600, height: 900 }, "cover")).toEqual({
      x: -311.1111111111111, y: 0, width: 1422.2222222222222, height: 800,
    });
    expect(mediaRect({ width: 300, height: 100 }, { width: 10, height: 10 }, "fill")).toEqual({
      x: 0, y: 0, width: 300, height: 100,
    });
  });

  it("returns an empty rect before the element or video has a size", () => {
    expect(mediaRect({ width: 0, height: 480 }, { width: 640, height: 480 }).width).toBe(0);
    expect(mediaRect({ width: 640, height: 480 }, { width: 0, height: 0 }).width).toBe(0);
  });
});

describe("toPixel", () => {
  it("maps normalised coordinates into the letterboxed rect", () => {
    const rect = mediaRect({ width: 800, height: 800 }, { width: 1920, height: 1080 });
    expect(toPixel({ x: 0, y: 0 }, rect)).toEqual({ x: 0, y: 175 });
    expect(toPixel({ x: 0.5, y: 0.5 }, rect)).toEqual({ x: 400, y: 400 });
    expect(toPixel({ x: 1, y: 1 }, rect)).toEqual({ x: 800, y: 625 });
  });
});

describe("canvasBackingSize", () => {
  it("scales by devicePixelRatio and never below 1x", () => {
    expect(canvasBackingSize({ width: 400, height: 225 }, 2)).toEqual({ width: 800, height: 450 });
    expect(canvasBackingSize({ width: 400, height: 225 }, 0)).toEqual({ width: 400, height: 225 });
  });
});

import { describe, expect, it } from "vitest";

import { createStatusBackoff, isTerminal, nextPollDelay, POLL_MAX_MS } from "./polling";

describe("nextPollDelay", () => {
  it("backs off exponentially from 1s", () => {
    expect([0, 1, 2].map(nextPollDelay)).toEqual([1000, 1500, 2250]);
  });

  it("caps at the maximum", () => {
    expect(nextPollDelay(50)).toBe(POLL_MAX_MS);
  });
});

describe("isTerminal", () => {
  it("is true only for succeeded and failed", () => {
    expect(isTerminal("succeeded")).toBe(true);
    expect(isTerminal("failed")).toBe(true);
    expect(isTerminal("rendering")).toBe(false);
    expect(isTerminal(undefined)).toBe(false);
  });
});

describe("createStatusBackoff", () => {
  it("backs off while the status is unchanged and resets on a transition", () => {
    const next = createStatusBackoff();
    expect(next("queued", 0)).toBe(1000);
    expect(next("queued", 1)).toBe(1500);
    expect(next("queued", 2)).toBe(2250);
    expect(next("extracting_pose", 3)).toBe(1000);
    expect(next("extracting_pose", 4)).toBe(1500);
    expect(next("succeeded", 5)).toBe(false);
  });
});

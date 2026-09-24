import { describe, expect, it } from "vitest";

import { isTerminal, nextPollDelay, POLL_MAX_MS } from "./polling";

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

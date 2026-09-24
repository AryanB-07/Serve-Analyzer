import { describe, expect, it } from "vitest";

import { ApiError } from "./client";
import { shouldRetry } from "./retry";

describe("shouldRetry", () => {
  it("retries network and server errors once", () => {
    expect(shouldRetry(0, new ApiError(0, "Network error"))).toBe(true);
    expect(shouldRetry(0, new ApiError(503, "Unavailable"))).toBe(true);
    expect(shouldRetry(0, new TypeError("Failed to fetch"))).toBe(true);
    expect(shouldRetry(1, new ApiError(503, "Unavailable"))).toBe(false);
  });

  it("never retries client errors", () => {
    expect(shouldRetry(0, new ApiError(404, "Analysis not found"))).toBe(false);
    expect(shouldRetry(0, new ApiError(409, "Analysis is queued"))).toBe(false);
  });
});

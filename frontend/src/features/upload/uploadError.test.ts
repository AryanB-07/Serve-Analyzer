import { describe, expect, it } from "vitest";

import { ApiError } from "../../api";
import { uploadErrorText } from "./uploadError";

describe("uploadErrorText", () => {
  it("shows a limit as a limit, without blaming the connection", () => {
    const text = uploadErrorText(new ApiError(429, "You can analyze up to 20 serves a day. Try again tomorrow."));
    expect(text).toEqual({ title: "Limit reached.", detail: "You can analyze up to 20 serves a day. Try again tomorrow." });
  });

  it("passes other refusals through as they are", () => {
    expect(uploadErrorText(new ApiError(413, "Videos must be under 200 MB")).detail).toBe("Videos must be under 200 MB");
  });

  it("suggests checking the connection for network and server errors", () => {
    expect(uploadErrorText(new ApiError(0, "Network error during upload")).detail).toContain("Check your connection");
    expect(uploadErrorText(new ApiError(503, "Service Unavailable")).detail).toContain("Check your connection");
  });
});

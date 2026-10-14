/** The HTTP client itself (the page tests use a fake one), with fetch stubbed. */
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, httpClient } from "./client";

function respond(status: number, body: string, contentType = "application/json") {
  const fetch = vi.fn(async () => new Response(status === 204 ? null : body, { status, headers: { "Content-Type": contentType } }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => vi.unstubAllGlobals());

describe("the HTTP client", () => {
  it("accepts 202 Accepted with no body (password reset, resend, email change)", async () => {
    respond(202, "");
    await expect(httpClient.requestPasswordReset("a@example.com")).resolves.toBeUndefined();
    respond(202, "");
    await expect(httpClient.resendVerification()).resolves.toBeUndefined();
    const fetch = respond(202, "");
    await expect(httpClient.requestEmailChange("new@example.com", "pw")).resolves.toBeUndefined();
    expect(fetch).toHaveBeenCalledWith("/api/auth/email-change", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ new_email: "new@example.com", password: "pw" }),
    }));
  });

  it("accepts 204 No Content", async () => {
    respond(204, "");
    await expect(httpClient.confirmEmailChange("tok")).resolves.toBeUndefined();
  });

  it("parses JSON bodies, including a null report", async () => {
    respond(200, "null");
    await expect(httpClient.getReport("a1")).resolves.toBeNull();
    const fetch = respond(200, JSON.stringify({ reason: "other", note: null, created_at: "2026-10-12T00:00:00Z" }));
    await expect(httpClient.reportAnalysis("a 1", { reason: "other" })).resolves.toMatchObject({ reason: "other" });
    expect(fetch).toHaveBeenCalledWith("/api/analyses/a%201/report", expect.objectContaining({ method: "PUT" }));
  });

  it("turns an error's detail into an ApiError", async () => {
    respond(409, JSON.stringify({ detail: "An account with this email already exists." }));
    const error = await httpClient.requestEmailChange("x@example.com", "pw").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 409, message: "An account with this email already exists." });
  });

  it("keeps the status text when an error body isn't JSON", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>Bad gateway</html>", { status: 502, statusText: "Bad Gateway" })));
    await expect(httpClient.exportData()).rejects.toMatchObject({ status: 502, message: "Bad Gateway" });
  });

  it("reads the public demo from the site's static files, never the API", async () => {
    const fetch = respond(200, JSON.stringify({ id: "demo-serve-1", status: "succeeded" }));
    await expect(httpClient.getAnalysis("demo-serve-1")).resolves.toMatchObject({ status: "succeeded" });
    await httpClient.getResult("demo-serve-1");
    await httpClient.getFrames("demo-serve-1");
    expect(fetch.mock.calls.map((c) => (c as unknown[])[0])).toEqual([
      "/mock/demo-serve-1/summary.json", "/mock/demo-serve-1/result.json", "/mock/demo-serve-1/frames.json",
    ]);
    await expect(httpClient.getReport("demo-serve-1")).resolves.toBeNull();
    expect(fetch).toHaveBeenCalledTimes(3);
  });

  it("still asks the API for every other analysis", async () => {
    const fetch = respond(200, JSON.stringify({ id: "abc" }));
    await httpClient.getAnalysis("abc");
    expect(fetch).toHaveBeenCalledWith("/api/analyses/abc", expect.anything());
  });
});

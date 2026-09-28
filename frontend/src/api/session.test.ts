import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, httpClient } from "./client";
import { createMockClient, MOCK_USER } from "./mockClient";
import { createQueryClient, sessionKey } from "./session";

function respond(status: number, body?: unknown) {
  return vi.fn(async () =>
    new Response(body === undefined ? null : JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("http client auth", () => {
  it("reports a missing session as null rather than an error", async () => {
    vi.stubGlobal("fetch", respond(401, { detail: "Sign in to continue." }));
    await expect(httpClient.getMe()).resolves.toBeNull();
  });

  it("treats logout's empty 204 as success", async () => {
    vi.stubGlobal("fetch", respond(204));
    await expect(httpClient.logOut()).resolves.toBeUndefined();
  });

  it("marks the session signed out when a data request gets 401", async () => {
    const queryClient = createQueryClient();
    queryClient.setQueryData(sessionKey, MOCK_USER);
    vi.stubGlobal("fetch", respond(401, { detail: "Sign in to continue." }));
    await expect(httpClient.listAnalyses()).rejects.toBeInstanceOf(ApiError);
    expect(queryClient.getQueryData(sessionKey)).toBeNull();
  });

  it("leaves the session alone for a wrong password", async () => {
    const queryClient = createQueryClient();
    queryClient.setQueryData(sessionKey, MOCK_USER);
    vi.stubGlobal("fetch", respond(401, { detail: "Incorrect email or password." }));
    await expect(httpClient.logIn({ email: "a@example.com", password: "nope" })).rejects.toMatchObject({
      status: 401,
      message: "Incorrect email or password.",
    });
    expect(queryClient.getQueryData(sessionKey)).toEqual(MOCK_USER);
  });

  it("sends credentials as JSON to the auth endpoints", async () => {
    const fetchMock = respond(201, MOCK_USER);
    vi.stubGlobal("fetch", fetchMock);
    await httpClient.signUp({ email: "a@example.com", password: "long enough" });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/auth/signup");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ email: "a@example.com", password: "long enough" });
  });
});

describe("mock client auth", () => {
  it("starts signed in, and signs out and in again", async () => {
    const client = createMockClient({ latencyMs: 0 });
    expect(await client.getMe()).toEqual(MOCK_USER);
    await client.logOut();
    expect(await client.getMe()).toBeNull();
    const user = await client.logIn({ email: " Coach@Example.com ", password: "whatever" });
    expect(user.email).toBe("coach@example.com");
    expect(await client.getMe()).toEqual(user);
  });
});

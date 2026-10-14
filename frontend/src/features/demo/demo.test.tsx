/** The public sample analysis: opens without an account, with nothing to delete or report. */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { makeResult } from "../../test/fixtures";
import type { User } from "../../api/types";

const fake = vi.hoisted(() => ({ user: null as unknown, getMe: vi.fn(), getAnalysis: vi.fn(), getResult: vi.fn(), getFrames: vi.fn(), getReport: vi.fn() }));

vi.mock("../../api", async () => {
  const client = await import("../../api/client");
  return { api: fake, USE_MOCKS: false, ApiError: client.ApiError, UploadAbortedError: client.UploadAbortedError };
});
// The charts and video need a real browser; the browser tests (e2e/demo.spec.ts) cover them.
vi.mock("../results/charts/AngleCharts", () => ({ AngleCharts: () => null }));
vi.mock("../results/VideoStage", () => ({ VideoStage: () => <div>video</div> }));

const { createQueryClient } = await import("../../api/session");
const { DemoPage } = await import("./DemoPage");

const SUMMARY = {
  id: "demo-serve-1", hand: "right", status: "succeeded", filename: "serve_week1.mp4",
  created_at: "2026-09-13T17:30:00Z", updated_at: "2026-09-13T17:30:00Z", error: null, thumbnail_url: null, counts: null,
};

beforeEach(() => {
  fake.user = null;
  fake.getMe.mockReset().mockImplementation(async () => fake.user);
  fake.getAnalysis.mockReset().mockResolvedValue(SUMMARY);
  const result = makeResult();
  fake.getResult.mockReset().mockResolvedValue({ ...result, id: "demo-serve-1" });
  fake.getFrames.mockReset().mockResolvedValue({ fps: result.fps, n_frames: result.n_frames, width: 640, height: 480, phases: result.phases, landmarks: { raw: {}, smoothed: {} }, series: {} });
  fake.getReport.mockReset().mockResolvedValue(null);
});

function renderDemo() {
  const router = createMemoryRouter([{ path: "/demo", element: <DemoPage /> }], { initialEntries: ["/demo"] });
  render(<QueryClientProvider client={createQueryClient()}><RouterProvider router={router} /></QueryClientProvider>);
}

describe("the public demo", () => {
  it("shows a real analysis to someone signed out, with ways to sign up", async () => {
    renderDemo();
    expect(await screen.findByRole("heading", { name: "Coaching feedback" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Sample analysis" })).toBeInTheDocument();
    expect(fake.getAnalysis).toHaveBeenCalledWith("demo-serve-1");
    expect(screen.getByRole("link", { name: "Create a free account" })).toHaveAttribute("href", "/signup");
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  });

  it("has nothing to delete or report", async () => {
    renderDemo();
    await screen.findByRole("heading", { name: "Coaching feedback" });
    expect(screen.queryByRole("button", { name: /Delete/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "This result looks wrong?" })).not.toBeInTheDocument();
    expect(screen.getByText("What this analysis can't do")).toBeInTheDocument();
  });

  it("credits the video and says it isn't filmed side-on", async () => {
    renderDemo();
    await screen.findByRole("heading", { name: "Sample analysis" });
    expect(screen.getByText(/CC BY 4.0/)).toHaveTextContent("Cacioppo et al. (2014)");
    expect(screen.getByText(/CC BY 4.0/)).toHaveTextContent("rather than side-on");
    expect(screen.getByRole("link", { name: "Wikimedia Commons" })).toHaveAttribute("href", expect.stringContaining("commons.wikimedia.org"));
  });

  it("points someone signed in at their own upload instead", async () => {
    fake.user = { id: "u1", email: "a@example.com", created_at: "", email_verified: true } satisfies User;
    renderDemo();
    expect(await screen.findByRole("link", { name: "Analyze your serve" })).toHaveAttribute("href", "/");
    expect(screen.queryByRole("link", { name: "Create a free account" })).not.toBeInTheDocument();
  });
});

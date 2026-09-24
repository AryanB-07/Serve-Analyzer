import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import type { AnalysisSummary, ErrorCode } from "../../api/types";
import { ERROR_COPY } from "./errorCopy";
import { ProcessingView, stageStates } from "./ProcessingView";

const summary = (overrides: Partial<AnalysisSummary> = {}): AnalysisSummary => ({
  id: "a1", hand: "right", status: "analyzing", filename: "serve.mp4",
  created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
  error: null, thumbnail_url: null, counts: null, ...overrides,
});

function renderView(s: AnalysisSummary, onRetry = vi.fn()) {
  render(
    <MemoryRouter>
      <ProcessingView summary={s} since={Date.now()} onRetry={onRetry} />
    </MemoryRouter>,
  );
  return onRetry;
}

describe("stageStates", () => {
  it("marks earlier stages done and later ones upcoming", () => {
    expect(stageStates("queued")).toEqual(["current", "upcoming", "upcoming", "upcoming"]);
    expect(stageStates("analyzing")).toEqual(["done", "done", "current", "upcoming"]);
    expect(stageStates("succeeded")).toEqual(["done", "done", "done", "done"]);
  });
});

describe("ProcessingView", () => {
  it("shows the stages with the current one announced", () => {
    renderView(summary({ status: "extracting_pose" }));
    expect(screen.getByRole("heading", { name: "Analyzing your serve" })).toBeInTheDocument();
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Queued (done)");
    expect(items[1]).toHaveTextContent("Tracking your body (in progress)");
    expect(items[3]).toHaveTextContent("Preparing video (not started)");
    expect(screen.getByRole("status")).toHaveTextContent("Tracking your body: Finding joints in every frame");
  });

  it.each(Object.keys(ERROR_COPY) as ErrorCode[])("has a friendly screen for %s", (code) => {
    renderView(summary({ status: "failed", error: { code, message: "Video is 16.2s long; the limit is 15s." } }));
    expect(screen.getByRole("alert")).toHaveTextContent(ERROR_COPY[code].title);
  });

  it("leads with a new upload when retrying can't help, and shows the server's specifics", () => {
    renderView(summary({ status: "failed", error: { code: "VIDEO_TOO_LONG", message: "Video is 16.2s long; the limit is 15s." } }));
    expect(screen.getByText("Video is 16.2s long; the limit is 15s.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upload a different video" }).className).toMatch(/bg-accent/);
  });

  it("links the filming guide when the person wasn't detected", () => {
    renderView(summary({ status: "failed", error: { code: "NO_PERSON_DETECTED", message: "" } }));
    expect(screen.getByRole("link", { name: "Read the filming guide" })).toHaveAttribute("href", "/#filming-guide");
  });

  it("retries", async () => {
    const onRetry = renderView(summary({ status: "failed", error: { code: "INTERNAL", message: "" } }));
    const retry = screen.getByRole("button", { name: "Try again" });
    expect(retry.className).toMatch(/bg-accent/);
    await userEvent.click(retry);
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("explains an upload that never finished", () => {
    renderView(summary({ status: "awaiting_upload" }));
    expect(screen.getByRole("heading", { name: "This upload didn't finish" })).toBeInTheDocument();
  });
});

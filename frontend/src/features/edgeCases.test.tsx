/** Edge cases for upload, mock API, shortcuts, error copy and page components. */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { ApiError, UploadAbortedError, type ApiClient } from "../api/client";
import { createMockClient } from "../api/mockClient";
import type { AnalysisSummary } from "../api/types";
import { createPlayheadStore } from "../playhead/store";
import { makeResult } from "../test/fixtures";
import { renderWithPlayhead } from "../test/playhead";
import { errorCopyFor, ERROR_COPY } from "./processing/errorCopy";
import { ProcessingView } from "./processing/ProcessingView";
import { MetricCards } from "./results/MetricCards";
import { applyShortcut, shortcutFor, shouldIgnore } from "./results/shortcuts";
import { runUpload } from "./upload/runUpload";
import { checkFile } from "./upload/validateVideo";

const summary = (id: string, overrides: Partial<AnalysisSummary> = {}): AnalysisSummary => ({
  id, hand: "right", status: "succeeded", filename: `${id}.mp4`,
  created_at: "2026-09-20T10:00:00Z", updated_at: "2026-09-20T10:00:00Z",
  error: null, thumbnail_url: null, counts: { good: 3, borderline: 1, off: 1, unknown: 0 }, ...overrides,
});

const listState = { current: [] as AnalysisSummary[] };
vi.mock("../api/queries", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  useAnalysesList: () => ({
    data: { pages: [{ items: listState.current, next_cursor: null }] },
    isPending: false, isError: false, hasNextPage: false, isFetchingNextPage: false,
    fetchNextPage: vi.fn(), refetch: vi.fn(),
  }),
}));
const { HistoryPage } = await import("./history/HistoryPage");

describe("upload flow edge cases", () => {
  it("reports a cancel during the create step as a cancel, not a failure", async () => {
    const controller = new AbortController();
    const client = {
      createAnalysis: vi.fn(async () => {
        controller.abort();
        return {
          analysis: summary("a", { status: "awaiting_upload" }),
          upload: { url: "/x", method: "PUT" as const, headers: {}, expires_at: "" },
        };
      }),
      uploadVideo: vi.fn(),
      startAnalysis: vi.fn(),
    } as unknown as ApiClient;
    const file = new File(["x"], "a.mp4", { type: "video/mp4" });
    await expect(
      runUpload(client, { file, hand: "right", contentType: "video/mp4" }, { signal: controller.signal }),
    ).rejects.toBeInstanceOf(UploadAbortedError);
    expect(client.uploadVideo).not.toHaveBeenCalled();
    expect(client.startAnalysis).not.toHaveBeenCalled();
  });

  it("validates awkward file names", () => {
    expect(checkFile({ name: "serve", type: "video/mp4", size: 10 })).toMatchObject({ ok: true });
    expect(checkFile({ name: "serve", type: "", size: 10 })).toMatchObject({ ok: false });
    expect(checkFile({ name: "my.serve.MOV", type: "", size: 10 })).toEqual({ ok: true, contentType: "video/quicktime" });
  });
});

describe("mock API contract", () => {
  const client = createMockClient({ latencyMs: 0, now: () => 0, fetchJson: async () => ({ items: [], next_cursor: null }) as never });
  const request = { hand: "right", filename: "s.mp4", content_type: "video/mp4", size_bytes: 1 } as const;

  it("mirrors the API's 404 and 409 rules", async () => {
    await expect(client.getAnalysis("nope")).rejects.toMatchObject({ status: 404 });
    const { analysis } = await client.createAnalysis(request);
    await expect(client.getFrames(analysis.id)).rejects.toMatchObject({ status: 409 });
    await expect(client.retryAnalysis(analysis.id)).rejects.toBeInstanceOf(ApiError);
    await client.startAnalysis(analysis.id);
    await expect(client.startAnalysis(analysis.id)).rejects.toMatchObject({ status: 409 });
  });

  it("cancels a simulated upload", async () => {
    const controller = new AbortController();
    controller.abort();
    const { upload } = await client.createAnalysis(request);
    await expect(client.uploadVideo(upload, new Blob(["x"]), () => {}, controller.signal)).rejects.toBeInstanceOf(
      UploadAbortedError,
    );
  });
});

describe("shortcuts at the edges", () => {
  it("does not treat Shift+1 ('!') as a phase jump", () => {
    expect(shortcutFor({ key: "!", shiftKey: true, metaKey: false, ctrlKey: false, altKey: false })).toBeNull();
  });

  it("stays inside the clip when stepping past either end", () => {
    const store = createPlayheadStore(10, 25);
    applyShortcut({ type: "stepSeconds", seconds: -1 }, store, { trophy: null, racket_drop: null, contact: null });
    expect(store.getState().frame).toBe(0);
    applyShortcut({ type: "stepSeconds", seconds: 1 }, store, { trophy: null, racket_drop: null, contact: null });
    expect(store.getState().frame).toBe(9);
  });

  it("lets Space toggle a focused switch instead of playback", () => {
    const el = document.createElement("div");
    el.setAttribute("role", "switch");
    expect(shouldIgnore(el, " ")).toBe(true);
    expect(shouldIgnore(null, " ")).toBe(false);
  });
});

describe("error copy", () => {
  it("falls back for codes this build doesn't know", () => {
    expect(errorCopyFor("QUOTA_EXCEEDED")).toBe(ERROR_COPY.INTERNAL);
    expect(errorCopyFor(undefined)).toBe(ERROR_COPY.INTERNAL);
    expect(errorCopyFor("FPS_TOO_LOW")).toBe(ERROR_COPY.FPS_TOO_LOW);
  });

  it("renders a failure with an unknown code instead of crashing", () => {
    const failed = summary("f", { status: "failed", error: { code: "QUOTA_EXCEEDED" as never, message: "" } });
    render(
      <MemoryRouter>
        <ProcessingView summary={failed} since={Date.now()} onRetry={() => {}} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(ERROR_COPY.INTERNAL.title);
  });
});

describe("MetricCards with nothing measured", () => {
  it("renders every card as not measured", () => {
    const none = { front_knee_flexion: null, back_knee_flexion: null, elbow_angle: null, trunk_tilt: null, wrist_height: null };
    const result = makeResult({
      phases: { trophy: null, racket_drop: null, contact: null },
      metrics: { trophy: none, racket_drop: none, contact: none },
    });
    renderWithPlayhead(<MetricCards result={result} />);
    expect(screen.getAllByTestId("metric-status").map((s) => s.textContent)).toEqual(Array(5).fill("Not measured"));
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });
});

function LocationProbe() {
  const location = useLocation();
  return <p data-testid="location">{location.pathname + location.search}</p>;
}

function renderHistory(items: AnalysisSummary[]) {
  listState.current = items;
  render(
    <MemoryRouter initialEntries={["/history"]}>
      <Routes>
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/compare" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("HistoryPage", () => {
  it("shows every status and only lets finished serves be compared", () => {
    renderHistory([
      summary("done"),
      summary("busy", { status: "extracting_pose", counts: null }),
      summary("broken", { status: "failed", counts: null, error: { code: "NO_PERSON_DETECTED", message: "" } }),
      summary("abandoned", { status: "awaiting_upload", counts: null }),
    ]);
    expect(screen.getByText("Processing…")).toBeInTheDocument();
    expect(screen.getByText(/Failed · We couldn't detect a person clearly/)).toBeInTheDocument();
    expect(screen.getByText("Upload not finished")).toBeInTheDocument();
    expect(screen.getAllByRole("checkbox")).toHaveLength(1);
    const done = screen.getByTestId("history-done");
    expect(within(done).getByText("3 good, 1 borderline, 1 need work")).toBeInTheDocument();
  });

  it("compares two picks as before (older) and after (newer)", async () => {
    renderHistory([
      summary("newer", { created_at: "2026-09-20T10:00:00Z" }),
      summary("older", { created_at: "2026-09-13T10:00:00Z" }),
    ]);
    const compare = () => screen.getByRole("button", { name: "Compare" });
    await userEvent.click(within(screen.getByTestId("history-newer")).getByRole("checkbox"));
    expect(compare()).toBeDisabled();
    await userEvent.click(within(screen.getByTestId("history-older")).getByRole("checkbox"));
    await userEvent.click(compare());
    expect(screen.getByTestId("location")).toHaveTextContent("/compare?a=older&b=newer");
  });

  it("shows an empty state", () => {
    renderHistory([]);
    expect(screen.getByText("No analyses yet")).toBeInTheDocument();
  });
});

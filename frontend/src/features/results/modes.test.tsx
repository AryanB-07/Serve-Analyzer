/** Simple and advanced results: scores and plain words, or exact angles with confidence. */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, renderHook, act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AnalysisResult } from "../../api/types";
import { likelyRange, uncertaintyFor } from "../../lib/confidence";
import { readingFor } from "../../lib/metricInfo";
import { MODE_KEY, useResultsMode } from "../../lib/useResultsMode";
import { makeResult } from "../../test/fixtures";
import { renderWithPlayhead } from "../../test/playhead";
import { FeedbackPanel } from "./FeedbackPanel";
import { MetricCard, MetricCards } from "./MetricCards";

const KNEE = { visibility: 0.92, noise: 1.8, camera_error: 26.5, camera_view_assumed: true };

function withConfidence(extra: Partial<AnalysisResult> = {}): AnalysisResult {
  const result = makeResult();
  return {
    ...result,
    confidence: { trophy: { front_knee_flexion: KNEE, trunk_tilt: { visibility: 0.41, noise: 0.6, camera_error: 2.3, camera_view_assumed: false } } },
    feedback: result.feedback.map((f) => ({ ...f, plain: f.metric ? "Sit a little less deep on your front knee." : f.text })),
    ...extra,
  } as AnalysisResult;
}

beforeEach(() => window.localStorage.clear());

describe("simple mode", () => {
  it("shows a score out of 100 on the slider instead of the angle", () => {
    const result = withConfidence();
    renderWithPlayhead(<MetricCard reading={readingFor("front_knee_flexion", result)} phases={result.phases} mode="simple" />);
    const card = screen.getByRole("article", { name: "Front knee bend" });
    // 86.2° against a good range of 50-80 and borderline to 95: borderline, a little past the edge.
    expect(within(card).getByTestId("score")).toHaveTextContent("68");
    expect(card).toHaveTextContent("/ 100");
    expect(within(card).getByRole("meter", { name: "Front knee bend score" })).toHaveAttribute("aria-valuenow", "68");
    expect(within(card).getByTestId("metric-status")).toHaveTextContent(/^Borderline$/);
    expect(card).not.toHaveTextContent("86");
    expect(card).not.toHaveTextContent("Good range");
    expect(within(card).queryByTestId("confidence")).not.toBeInTheDocument();
  });

  it("marks a score from an approximate angle as rough", () => {
    const result = withConfidence({ camera_view: "front", quality: { trophy: { front_knee_flexion: "approximate" } } } as Partial<AnalysisResult>);
    renderWithPlayhead(<MetricCard reading={readingFor("front_knee_flexion", result)} phases={result.phases} mode="simple" />);
    const card = screen.getByRole("article", { name: "Front knee bend" });
    expect(within(card).getByTestId("score")).toHaveTextContent("≈68");
    expect(card).toHaveTextContent("rough from this angle");
  });

  it("leads with an overall serve score from the key positions that were measured", () => {
    renderWithPlayhead(<MetricCards result={withConfidence()} mode="simple" />);
    const overall = screen.getByRole("region", { name: "Serve score" });
    const scores = screen.getAllByTestId("score").map((el) => Number(el.textContent));
    const expected = Math.round(scores.reduce((a, b) => a + b, 0) / scores.length);
    expect(within(overall).getByTestId("overall-score")).toHaveTextContent(String(expected));
    expect(overall).toHaveTextContent(`The average of ${scores.length} key positions`);
  });

  it("gives feedback without numbers", () => {
    renderWithPlayhead(<FeedbackPanel result={withConfidence()} mode="simple" />);
    expect(screen.getAllByText("Sit a little less deep on your front knee.").length).toBeGreaterThan(0);
    expect(screen.queryByText(/86°/)).not.toBeInTheDocument();
  });

  it("falls back to the full feedback for results from before plain versions existed", () => {
    renderWithPlayhead(<FeedbackPanel result={makeResult()} mode="simple" />);
    expect(screen.getByText(/86°, target 50-80°/)).toBeInTheDocument();
  });
});

describe("advanced mode", () => {
  it("shows the exact angle, its likely range, and how confident the tracking was", () => {
    const result = withConfidence();
    const reading = readingFor("front_knee_flexion", result);
    renderWithPlayhead(
      <MetricCard reading={reading} phases={result.phases} mode="advanced" uncertainty={uncertaintyFor(result, "trophy", "front_knee_flexion")} />,
    );
    const card = screen.getByRole("article", { name: "Front knee bend" });
    expect(card).toHaveTextContent("86.2°");
    expect(within(card).getByTestId("metric-status")).toHaveTextContent("Borderline: a little high");
    const details = within(card).getByTestId("confidence");
    // ±(26.5 camera + 1.8 noise) = ±28.3
    expect(details).toHaveTextContent("Likely range57.9° to 114.5° (±28.3°)");
    expect(details).toHaveTextContent("Tracking confidence92% · high");
    expect(details).toHaveTextContent("Tracking noise±1.8°");
    expect(details).toHaveTextContent("Camera angle errorup to ±26.5° if filmed side-on, as the guide says");
    expect(within(card).getByTestId("likely-band")).toBeInTheDocument();
  });

  it("says when the camera position was given, and flags low tracking confidence", () => {
    const result = withConfidence();
    renderWithPlayhead(
      <MetricCard reading={readingFor("trunk_tilt", result)} phases={result.phases} mode="advanced" uncertainty={uncertaintyFor(result, "trophy", "trunk_tilt")} />,
    );
    const details = within(screen.getByRole("article", { name: "Trunk tilt" })).getByTestId("confidence");
    expect(details).toHaveTextContent("41% · low");
    expect(details).toHaveTextContent("from your camera position");
  });

  it("says so when an older analysis has no confidence numbers", () => {
    const result = makeResult();
    renderWithPlayhead(<MetricCard reading={readingFor("front_knee_flexion", result)} phases={result.phases} mode="advanced" />);
    expect(screen.getByText("Confidence details aren't available for this analysis.")).toBeInTheDocument();
  });

  it("has no overall score", () => {
    renderWithPlayhead(<MetricCards result={withConfidence()} mode="advanced" />);
    expect(screen.queryByRole("region", { name: "Serve score" })).not.toBeInTheDocument();
  });

  it("keeps the likely range above zero", () => {
    expect(likelyRange(5, { visibility: 1, level: "high", noise: 1, cameraError: 20, assumed: true, margin: 21 })).toEqual([0, 26]);
    expect(likelyRange(null, null)).toBeNull();
  });
});

describe("the remembered mode", () => {
  it("starts simple and remembers a change", () => {
    const { result, unmount } = renderHook(() => useResultsMode());
    expect(result.current[0]).toBe("simple");
    act(() => result.current[1]("advanced"));
    expect(window.localStorage.getItem(MODE_KEY)).toBe("advanced");
    unmount();
    expect(renderHook(() => useResultsMode()).result.current[0]).toBe("advanced");
  });

  it("still works when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    const { result } = renderHook(() => useResultsMode());
    expect(result.current[0]).toBe("simple");
    act(() => result.current[1]("advanced"));
    expect(result.current[0]).toBe("advanced");
    vi.restoreAllMocks();
  });
});

// --- the whole results page -------------------------------------------------------------------

const fake = vi.hoisted(() => ({ getMe: vi.fn(), getAnalysis: vi.fn(), getResult: vi.fn(), getFrames: vi.fn(), getReport: vi.fn() }));
vi.mock("../../api", async () => {
  const client = await import("../../api/client");
  return { api: fake, USE_MOCKS: false, ApiError: client.ApiError, UploadAbortedError: client.UploadAbortedError };
});
vi.mock("./charts/AngleCharts", () => ({ AngleCharts: () => <section aria-label="Angle charts">charts</section> }));
vi.mock("./VideoStage", () => ({ VideoStage: () => <div>video</div> }));

describe("switching modes on the results page", () => {
  it("hides the charts and angle-label controls in simple mode, and shows them in advanced", async () => {
    const { createQueryClient } = await import("../../api/session");
    const { ResultsPage } = await import("./ResultsPage");
    const { HelpProvider } = await import("../help/HelpProvider");
    const result = withConfidence();
    fake.getMe.mockResolvedValue(null);
    fake.getAnalysis.mockResolvedValue({ id: "a1", hand: "right", status: "succeeded", filename: "serve.mp4", created_at: "2026-10-14T10:00:00Z", updated_at: "2026-10-14T10:00:00Z" });
    fake.getResult.mockResolvedValue(result);
    fake.getFrames.mockResolvedValue({ fps: result.fps, n_frames: result.n_frames, width: 640, height: 480, phases: result.phases, landmarks: { raw: {}, smoothed: {} }, series: {} });
    fake.getReport.mockResolvedValue(null);
    const router = createMemoryRouter(
      [{ path: "/analyses/:id", element: <HelpProvider><ResultsPage /></HelpProvider> }],
      { initialEntries: ["/analyses/a1"] },
    );
    render(<QueryClientProvider client={createQueryClient()}><RouterProvider router={router} /></QueryClientProvider>);

    const simple = await screen.findByRole("radio", { name: "Simple" });
    expect(simple).toBeChecked();
    expect(screen.queryByRole("region", { name: "Angle charts" })).not.toBeInTheDocument();
    expect(screen.queryByRole("switch", { name: "Angle labels" })).not.toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Skeleton" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Serve score" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("radio", { name: "Advanced" }));
    expect(screen.getByRole("region", { name: "Angle charts" })).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Angle labels" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Serve score" })).not.toBeInTheDocument();
    expect(screen.getAllByTestId("confidence").length).toBeGreaterThan(0);

    await userEvent.click(screen.getByRole("button", { name: "What do these mean?" }));
    expect(screen.getByRole("tab", { name: "Reading your results" })).toHaveAttribute("aria-selected", "true");
  });
});

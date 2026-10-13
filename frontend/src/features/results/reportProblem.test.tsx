/** "This result looks wrong", the known limits, and the "not a serve" failure, against a fake backend. */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
// The app's RouterProvider (main.tsx): only this one honours navigate()'s flushSync.
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AnalysisSummary, Report, ReportRequest } from "../../api/types";

const fake = vi.hoisted(() => ({
  getMe: vi.fn(),
  getAnalysis: vi.fn(),
  getReport: vi.fn(),
  reportAnalysis: vi.fn(),
  retryAnalysis: vi.fn(),
}));

vi.mock("../../api", async () => {
  const client = await import("../../api/client");
  return { api: fake, USE_MOCKS: false, ApiError: client.ApiError, UploadAbortedError: client.UploadAbortedError };
});

// The charts pull in uPlot, which needs a real browser; the failure screen never shows them.
vi.mock("./charts/AngleCharts", () => ({ AngleCharts: () => null }));

const { ApiError } = await import("../../api/client");
const { createQueryClient } = await import("../../api/session");
const { ReportProblem, REASONS, REASON_LABELS } = await import("./ReportProblem");
const { ResultsPage } = await import("./ResultsPage");
const { KnownLimits, LIMITS } = await import("../../components/KnownLimits");

const NOT_A_SERVE: AnalysisSummary = {
  id: "a1", hand: "right", status: "failed", filename: "forehand.mov",
  created_at: "2026-10-12T10:00:00Z", updated_at: "2026-10-12T10:01:00Z",
  error: { code: "NOT_A_SERVE", message: "This doesn't look like a serve. Your hitting wrist never got above your head." },
  thumbnail_url: null, counts: null,
};

let saved: Report | null;

beforeEach(() => {
  saved = null;
  fake.getMe.mockReset().mockResolvedValue({ id: "u1", email: "a@example.com", created_at: "", email_verified: true });
  fake.getAnalysis.mockReset().mockResolvedValue(NOT_A_SERVE);
  fake.getReport.mockReset().mockImplementation(async () => saved);
  fake.reportAnalysis.mockReset().mockImplementation(async (_id: string, body: ReportRequest) => {
    saved = { reason: body.reason, note: body.note ?? null, created_at: "2026-10-12T10:05:00Z" };
    return saved;
  });
});

function renderAt(element: React.ReactNode, path = "/analyses/a1") {
  const router = createMemoryRouter(
    [
      { path: "/analyses/:id", element },
      { path: "/", element: <h1>Upload page</h1> },
    ],
    { initialEntries: [path] },
  );
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

describe("reporting a finished result", () => {
  it("sends the chosen reason and note, then thanks you", async () => {
    renderAt(<ReportProblem analysisId="a1" outcome="succeeded" />);
    await userEvent.click(await screen.findByRole("button", { name: "This result looks wrong?" }));
    const form = screen.getByRole("form", { name: "What looks wrong?" });
    const send = within(form).getByRole("button", { name: "Send" });
    expect(send).toBeDisabled();
    expect(within(form).getAllByRole("radio").map((r) => r.closest("label")!.textContent)).toEqual(
      REASONS.succeeded.map((r) => REASON_LABELS[r]),
    );
    await userEvent.click(within(form).getByLabelText("A phase is marked at the wrong moment"));
    await userEvent.type(within(form).getByLabelText(/Anything to add/), "  contact is early  ");
    await userEvent.click(send);
    expect(fake.reportAnalysis).toHaveBeenCalledWith("a1", { reason: "wrong_phases", note: "contact is early" });
    expect(await screen.findByRole("status")).toHaveTextContent("Thanks, we've noted that: a phase is marked at the wrong moment.");
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
  });

  it("shows a report sent earlier, and lets you change it", async () => {
    saved = { reason: "not_a_serve", note: "a smash", created_at: "2026-10-11T10:00:00Z" };
    renderAt(<ReportProblem analysisId="a1" outcome="succeeded" />);
    expect(await screen.findByRole("status")).toHaveTextContent("this isn't a serve");
    await userEvent.click(screen.getByRole("button", { name: "Change" }));
    expect(screen.getByLabelText("This isn't a serve")).toBeChecked();
    expect(screen.getByLabelText(/Anything to add/)).toHaveValue("a smash");
  });

  it("keeps the form open and explains a failure", async () => {
    fake.reportAnalysis.mockRejectedValue(new ApiError(404, "Analysis not found"));
    renderAt(<ReportProblem analysisId="a1" outcome="succeeded" />);
    await userEvent.click(await screen.findByRole("button", { name: "This result looks wrong?" }));
    await userEvent.click(screen.getByLabelText("Something else"));
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Analysis not found");
    expect(screen.getByRole("form")).toBeInTheDocument();
  });

  it("says what happens to the report", async () => {
    renderAt(<ReportProblem analysisId="a1" outcome="succeeded" />);
    await userEvent.click(await screen.findByRole("button", { name: "This result looks wrong?" }));
    expect(screen.getByText(/deleted when you delete the analysis/)).toBeInTheDocument();
  });
});

describe("the \"doesn't look like a serve\" screen", () => {
  it("explains the rejection and lets you say it was a serve", async () => {
    renderAt(<ResultsPage />);
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByRole("heading", { name: "This doesn't look like a serve" })).toBeInTheDocument();
    expect(alert).toHaveTextContent("Your hitting wrist never got above your head.");
    expect(alert.textContent!.match(/This doesn't look like a serve/g)).toHaveLength(1);
    expect(alert).toHaveTextContent("Forehands, backhands and smashes can't be analysed yet.");
    expect(within(alert).getByRole("link", { name: "Read the filming guide" })).toHaveAttribute("href", "/#filming-guide");
    expect(within(alert).getByRole("link", { name: "Upload a different video" })).toHaveAttribute("href", "/");

    await userEvent.click(within(alert).getByRole("button", { name: "This was a serve? Tell us" }));
    expect(screen.getByLabelText("This was a serve")).toBeChecked();
    expect(screen.getAllByRole("radio")).toHaveLength(REASONS.failed.length);
    await userEvent.type(screen.getByLabelText(/Anything to add/), "kick serve from behind");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(fake.reportAnalysis).toHaveBeenCalledWith("a1", { reason: "was_a_serve", note: "kick serve from behind" });
    expect(await screen.findByText(/we've noted that/)).toHaveTextContent("this was a serve");
  });

  it("offers no report on other failures", async () => {
    fake.getAnalysis.mockResolvedValue({ ...NOT_A_SERVE, error: { code: "NO_PERSON_DETECTED", message: "" } });
    renderAt(<ResultsPage />);
    expect(await screen.findByRole("heading", { name: "We couldn't detect a person clearly" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /This was a serve/ })).not.toBeInTheDocument();
    expect(fake.getReport).not.toHaveBeenCalled();
  });
});

describe("known limits", () => {
  it("lists each limit behind a disclosure", async () => {
    renderAt(<KnownLimits />);
    const summary = await screen.findByText("What this analysis can't do");
    const details = summary.closest("details")!;
    expect(details.open).toBe(false);
    await userEvent.click(summary);
    expect(details.open).toBe(true);
    for (const [title] of LIMITS) expect(within(details).getByText(title)).toBeInTheDocument();
    expect(details).toHaveTextContent("A swing that misses the ball looks just like a serve");
    expect(details).toHaveTextContent("Smashes");
  });
});

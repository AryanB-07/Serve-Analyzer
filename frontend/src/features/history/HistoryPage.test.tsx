/** History: score cards, the filter sidebar, details and notes, against a fake backend. */
import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
// The app's RouterProvider (main.tsx): only this one honours navigate()'s flushSync.
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AnalysisSummary } from "../../api/types";

const fake = vi.hoisted(() => ({
  items: [] as AnalysisSummary[],
  listAnalyses: vi.fn(),
  setNote: vi.fn(),
}));

vi.mock("../../api", async () => {
  const client = await import("../../api/client");
  return { api: fake, USE_MOCKS: false, ApiError: client.ApiError, UploadAbortedError: client.UploadAbortedError };
});

const { createQueryClient } = await import("../../api/session");
const { HistoryPage } = await import("./HistoryPage");

const summary = (id: string, overrides: Partial<AnalysisSummary> = {}): AnalysisSummary => ({
  id, hand: "right", status: "succeeded", filename: `${id}.mp4`,
  created_at: "2026-10-10T18:05:00Z", updated_at: "2026-10-10T18:05:00Z",
  error: null, thumbnail_url: null, counts: { good: 3, borderline: 1, off: 1, unknown: 0 },
  overall_score: 84, note: null,
  key_scores: {
    front_knee_flexion: { phase: "trophy", value: 65, score: 100, band: "good" },
    back_knee_flexion: null,
    trunk_tilt: { phase: "trophy", value: 40, score: 63, band: "borderline" },
    elbow_angle: { phase: "contact", value: 170, score: 100, band: "good" },
    wrist_height: { phase: "contact", value: 1.0, score: 21, band: "off" },
  },
  ...overrides,
});

beforeEach(() => {
  fake.items = [summary("a1")];
  fake.listAnalyses.mockReset().mockImplementation(async () => ({ items: fake.items, next_cursor: null }));
  fake.setNote.mockReset().mockImplementation(async (id: string, note: string) => {
    const trimmed = note.trim() || null;
    fake.items = fake.items.map((a) => (a.id === id ? { ...a, note: trimmed } : a));
    return fake.items.find((a) => a.id === id)!;
  });
});

function renderAt(path = "/history") {
  const router = createMemoryRouter(
    [
      { path: "/history", element: <HistoryPage /> },
      { path: "/analyses/:id", element: <h1>Results</h1> },
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

const lastQuery = () => fake.listAnalyses.mock.calls.at(-1)?.[1];

describe("a serve's card", () => {
  it("shows the score in its band's colour, the upload time and the counts", async () => {
    renderAt();
    const card = await screen.findByTestId("history-a1");
    const score = within(card).getByTestId("history-score");
    expect(score).toHaveTextContent("84");
    expect(score.className).toMatch(/text-good/);
    expect(within(card).getByRole("meter", { name: "Serve score" })).toHaveAttribute("aria-valuenow", "84");
    expect(within(card).getByText("Good")).toBeInTheDocument();
    expect(within(card).getByText((_, el) => el?.tagName === "TIME")).toHaveAttribute("datetime", "2026-10-10T18:05:00Z");
    expect(within(card).getByText("3 good, 1 borderline, 1 need work")).toBeInTheDocument();
  });

  it("hides the key positions until you ask for them", async () => {
    renderAt();
    const card = await screen.findByTestId("history-a1");
    expect(within(card).queryByRole("meter", { name: "Trunk tilt score" })).not.toBeInTheDocument();
    const toggle = within(card).getByRole("button", { name: "Show details" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(within(card).getByRole("meter", { name: "Trunk tilt score" })).toHaveAttribute("aria-valuenow", "63");
    expect(within(card).getByRole("meter", { name: "Contact height score" })).toHaveAttribute("aria-valuenow", "21");
    expect(within(card).getByText("Not measured")).toBeInTheDocument(); // the back knee
    expect(within(card).getByRole("link", { name: "Open the full analysis" })).toHaveAttribute("href", "/analyses/a1");
    await userEvent.click(within(card).getByRole("button", { name: "Hide details" }));
    expect(within(card).queryByRole("meter", { name: "Trunk tilt score" })).not.toBeInTheDocument();
  });

  it("colours a low score as needing work and leaves unscored serves without one", async () => {
    fake.items = [
      summary("low", { overall_score: 31 }),
      summary("none", { overall_score: null, key_scores: null }),
      summary("busy", { status: "extracting_pose", counts: null, overall_score: null, key_scores: null }),
    ];
    renderAt();
    const low = within(await screen.findByTestId("history-low")).getByTestId("history-score");
    expect(low.className).toMatch(/text-bad/);
    expect(within(screen.getByTestId("history-none")).getByText("No score")).toBeInTheDocument();
    const busy = screen.getByTestId("history-busy");
    expect(within(busy).queryByTestId("history-score")).not.toBeInTheDocument();
    expect(within(busy).queryByRole("button", { name: "Show details" })).not.toBeInTheDocument();
    expect(within(busy).getByText("Processing…")).toBeInTheDocument();
  });
});

describe("notes", () => {
  it("adds, edits and clears a note", async () => {
    renderAt();
    const card = await screen.findByTestId("history-a1");
    await userEvent.click(within(card).getByRole("button", { name: "Add a note to a1.mp4" }));
    const box = within(card).getByLabelText("Note on a1.mp4");
    await userEvent.type(box, "New toss, windy");
    expect(within(card).getByText("15/1000")).toBeInTheDocument();
    await userEvent.click(within(card).getByRole("button", { name: "Save note" }));
    expect(fake.setNote).toHaveBeenCalledWith("a1", "New toss, windy");
    expect(await within(card).findByTestId("history-note")).toHaveTextContent("New toss, windy");

    await userEvent.click(within(card).getByRole("button", { name: "Edit the note on a1.mp4" }));
    const again = within(card).getByLabelText("Note on a1.mp4");
    expect(again).toHaveValue("New toss, windy");
    await userEvent.clear(again);
    await userEvent.click(within(card).getByRole("button", { name: "Save note" }));
    expect(fake.setNote).toHaveBeenLastCalledWith("a1", "");
    expect(await within(card).findByRole("button", { name: "Add a note to a1.mp4" })).toBeInTheDocument();
  });

  it("cancelling leaves the note as it was", async () => {
    fake.items = [summary("a1", { note: "Felt loose" })];
    renderAt();
    const card = await screen.findByTestId("history-a1");
    expect(within(card).getByTestId("history-note")).toHaveTextContent("Felt loose");
    await userEvent.click(within(card).getByRole("button", { name: "Edit the note on a1.mp4" }));
    await userEvent.type(within(card).getByLabelText("Note on a1.mp4"), " and fast");
    await userEvent.click(within(card).getByRole("button", { name: "Cancel" }));
    expect(within(card).getByTestId("history-note")).toHaveTextContent(/^Felt loose$/);
    expect(fake.setNote).not.toHaveBeenCalled();
  });

  it("can't go past the length limit, and says when saving fails", async () => {
    fake.setNote.mockRejectedValueOnce(new Error("offline"));
    renderAt();
    const card = await screen.findByTestId("history-a1");
    await userEvent.click(within(card).getByRole("button", { name: "Add a note to a1.mp4" }));
    const box = within(card).getByLabelText("Note on a1.mp4");
    expect(box).toHaveAttribute("maxLength", "1000");
    await userEvent.type(box, "hi");
    await userEvent.click(within(card).getByRole("button", { name: "Save note" }));
    expect(await within(card).findByRole("alert")).toBeInTheDocument();
    expect(box).toHaveValue("hi"); // still editing, nothing lost
  });
});

describe("the filter sidebar", () => {
  it("asks the API for the chosen filters and keeps them in the URL", async () => {
    const router = renderAt();
    await screen.findByTestId("history-a1");
    expect(lastQuery()).toEqual({});
    const sidebar = screen.getByRole("complementary", { name: "Filters" });

    await userEvent.click(within(sidebar).getByRole("radio", { name: "80–100 · good" }));
    expect(router.state.location.search).toBe("?score=good");
    expect(lastQuery()).toEqual({ min_score: "80", max_score: "100" });

    await userEvent.selectOptions(within(sidebar).getByLabelText("Position"), "trunk_tilt");
    await userEvent.selectOptions(within(sidebar).getByLabelText("Rated"), "borderline");
    expect(router.state.location.search).toBe("?score=good&stat=trunk_tilt&band=borderline");
    expect(lastQuery()).toEqual({ min_score: "80", max_score: "100", stat: "trunk_tilt", stat_band: "borderline" });

    await userEvent.click(within(sidebar).getByRole("radio", { name: "Last 30 days" }));
    expect(lastQuery()).toHaveProperty("uploaded_from");

    await userEvent.click(within(sidebar).getByRole("button", { name: "Clear filters" }));
    expect(router.state.location.search).toBe("");
    expect(lastQuery()).toEqual({});
  });

  it("offers dates for a custom range", async () => {
    const router = renderAt();
    await screen.findByTestId("history-a1");
    const sidebar = screen.getByRole("complementary", { name: "Filters" });
    expect(within(sidebar).queryByLabelText("From")).not.toBeInTheDocument();
    await userEvent.click(within(sidebar).getByRole("radio", { name: "Between dates" }));
    await userEvent.type(within(sidebar).getByLabelText("From"), "2026-09-01");
    expect(router.state.location.search).toBe("?time=custom&from=2026-09-01");
    expect(lastQuery()).toEqual({ uploaded_from: new Date(2026, 8, 1).toISOString() });
  });

  it("opens with the filters a link carries", async () => {
    renderAt("/history?score=off&stat=wrist_height&band=off");
    await screen.findByTestId("history-a1");
    const sidebar = screen.getByRole("complementary", { name: "Filters" });
    expect(within(sidebar).getByRole("radio", { name: "0–49 · needs work" })).toBeChecked();
    expect(within(sidebar).getByLabelText("Position")).toHaveValue("wrist_height");
    expect(lastQuery()).toEqual({ min_score: "0", max_score: "49", stat: "wrist_height", stat_band: "off" });
  });

  it("follows the URL when it changes on its own", async () => {
    const router = renderAt("/history?score=good");
    await screen.findByTestId("history-a1");
    await act(() => router.navigate("/history?score=off&stat=trunk_tilt&band=good"));
    expect(screen.getByRole("radio", { name: "0–49 · needs work" })).toBeChecked();
    expect(screen.getByLabelText("Position")).toHaveValue("trunk_tilt");
    expect(lastQuery()).toEqual({ min_score: "0", max_score: "49", stat: "trunk_tilt", stat_band: "good" });
  });

  it("says when nothing matches, and clears from there", async () => {
    fake.listAnalyses.mockImplementation(async (_c: unknown, q: Record<string, string>) =>
      ({ items: q.min_score ? [] : fake.items, next_cursor: null }));
    renderAt("/history?score=good");
    expect(await screen.findByText("No serves match these filters")).toBeInTheDocument();
    expect(screen.queryByText("No analyses yet")).not.toBeInTheDocument();
    const clears = screen.getAllByRole("button", { name: "Clear filters" });
    await userEvent.click(clears.at(-1)!);
    expect(await screen.findByTestId("history-a1")).toBeInTheDocument();
  });

  it("folds away on small screens behind a toggle", async () => {
    renderAt();
    await screen.findByTestId("history-a1");
    const toggle = screen.getByRole("button", { name: /^Filters/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });
});

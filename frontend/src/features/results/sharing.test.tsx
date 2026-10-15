/** Sending serves: a friend's serve opens read-only, yours can be sent, and serves show in messages. */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
// The app's RouterProvider (main.tsx): only this one honours navigate()'s flushSync.
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AnalysisSummary, ConversationSummary, Message } from "../../api/types";
import { makeResult } from "../../test/fixtures";

const BOB = { username: "bob", display_name: "Bob B", avatar_url: null };
const MINE: AnalysisSummary = {
  id: "mine1", hand: "right", status: "succeeded", filename: "tuesday.mp4", created_at: "2026-10-10T10:00:00Z",
  updated_at: "2026-10-10T10:00:00Z", error: null, thumbnail_url: null, overall_score: 74, note: "my note", shared_by: null,
};
const THEIRS: AnalysisSummary = { ...MINE, id: "theirs1", filename: "Shared serve", note: null, shared_by: BOB, overall_score: 81 };
const CONV: ConversationSummary = { id: "c1", person: BOB, unread: 0, can_send: true, why_not: null, last_message: null };

const fake = vi.hoisted(() => ({
  analysis: null as unknown as AnalysisSummary,
  messages: [] as Message[],
  getMe: vi.fn(),
  getProfile: vi.fn(),
  getAnalysis: vi.fn(),
  getResult: vi.fn(),
  getFrames: vi.fn(),
  getReport: vi.fn(),
  listAnalyses: vi.fn(),
  listFollowPage: vi.fn(),
  startConversation: vi.fn(),
  sendMessage: vi.fn(),
  getConversation: vi.fn(),
  listMessages: vi.fn(),
  markRead: vi.fn(),
}));

vi.mock("../../api", async () => {
  const client = await import("../../api/client");
  return { api: fake, USE_MOCKS: false, ApiError: client.ApiError, UploadAbortedError: client.UploadAbortedError };
});
vi.mock("./charts/AngleCharts", () => ({ AngleCharts: () => <section aria-label="Angle charts">charts</section> }));
vi.mock("./VideoStage", () => ({ VideoStage: () => <div>video</div> }));

const { createQueryClient } = await import("../../api/session");
const { HelpProvider } = await import("../help/HelpProvider");
const { ConversationPage } = await import("../messages/ConversationPage");
const { ResultsPage } = await import("./ResultsPage");

beforeEach(() => {
  const result = makeResult();
  fake.analysis = MINE;
  fake.messages = [];
  fake.getMe.mockReset().mockResolvedValue(null);
  fake.getProfile.mockReset().mockResolvedValue({ username: "alice" });
  fake.getAnalysis.mockReset().mockImplementation(async () => fake.analysis);
  fake.getResult.mockReset().mockResolvedValue(result);
  fake.getFrames.mockReset().mockResolvedValue({ fps: result.fps, n_frames: result.n_frames, width: 640, height: 480,
    phases: result.phases, landmarks: { raw: {}, smoothed: {} }, series: {} });
  fake.getReport.mockReset().mockResolvedValue(null);
  fake.listAnalyses.mockReset().mockResolvedValue({ items: [MINE, { ...MINE, id: "mine2", filename: "monday.mp4" }], next_cursor: null });
  fake.listFollowPage.mockReset().mockResolvedValue({
    items: [{ person: BOB, since: "2026-09-02T10:00:00Z", you_follow: true, follows_you: true }], next_cursor: null,
  });
  fake.startConversation.mockReset().mockResolvedValue(CONV);
  fake.sendMessage.mockReset().mockImplementation(async (_id: string, message: { body?: string | null; analysis_id?: string | null }) => {
    const m: Message = { id: `m${fake.messages.length + 1}`, from_you: true, body: message.body ?? null, deleted: false,
      created_at: "2026-10-14T10:00:00Z",
      serve: message.analysis_id ? { analysis_id: message.analysis_id, available: true, overall_score: 74, recorded_at: MINE.created_at, thumbnail_url: null } : null };
    fake.messages = [m, ...fake.messages];
    return m;
  });
  fake.getConversation.mockReset().mockResolvedValue(CONV);
  fake.listMessages.mockReset().mockImplementation(async () => ({ items: fake.messages, next_cursor: null, seen_up_to: null }));
  fake.markRead.mockReset().mockResolvedValue(undefined);
});

function renderAt(path: string) {
  const router = createMemoryRouter(
    [
      { path: "/analyses/:id", element: <HelpProvider><ResultsPage /></HelpProvider> },
      { path: "/messages/:id", element: <ConversationPage /> },
      { path: "/compare", element: <h1>Compare page</h1> },
    ],
    { initialEntries: [path] },
  );
  render(<QueryClientProvider client={createQueryClient()}><RouterProvider router={router} /></QueryClientProvider>);
  return router;
}

describe("a serve a friend sent you", () => {
  it("opens read-only: named by its owner, with nothing to delete, report or send on", async () => {
    fake.analysis = THEIRS;
    renderAt("/analyses/theirs1");
    expect(await screen.findByRole("heading", { level: 1, name: "Bob B's serve" })).toBeInTheDocument();
    expect(screen.getByText("Shared by Bob B")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Delete/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send to a friend" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /looks wrong/ })).not.toBeInTheDocument();
    expect(fake.getReport).not.toHaveBeenCalled(); // owner-only: it would be a 404
  });

  it("compares with one of your serves", async () => {
    fake.analysis = THEIRS;
    const router = renderAt("/analyses/theirs1");
    await userEvent.click(await screen.findByRole("button", { name: "Compare with one of my serves" }));
    const picker = screen.getByRole("group", { name: "Compare with which of your serves?" });
    await userEvent.click(within(picker).getByRole("button", { name: /monday\.mp4/ }));
    expect(router.state.location.pathname + router.state.location.search).toBe("/compare?a=mine2&b=theirs1");
  });
});

describe("your own serve", () => {
  it("can be sent to a friend from its results page", async () => {
    renderAt("/analyses/mine1");
    await userEvent.click(await screen.findByRole("button", { name: "Send to a friend" }));
    await userEvent.click(await screen.findByRole("button", { name: /Bob B/ }));
    expect(fake.startConversation).toHaveBeenCalledWith("bob");
    expect(fake.sendMessage).toHaveBeenCalledWith("c1", { analysis_id: "mine1" });
    expect(await screen.findByRole("status")).toHaveTextContent("Sent to Bob B.");
    expect(screen.getByRole("link", { name: "Open the conversation" })).toHaveAttribute("href", "/messages/c1");
  });

  it("still has its delete and report controls", async () => {
    renderAt("/analyses/mine1");
    expect(await screen.findByRole("heading", { level: 1, name: "tuesday.mp4" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Delete/ })).toBeInTheDocument();
  });
});

describe("serves in messages", () => {
  it("are sent from the composer, with what was typed as the caption", async () => {
    renderAt("/messages/c1");
    await userEvent.type(await screen.findByLabelText("Message"), "Look at this one");
    await userEvent.click(screen.getByRole("button", { name: "Send a serve" }));
    const picker = screen.getByRole("group", { name: "Send one of your serves" });
    await userEvent.click(within(picker).getByRole("button", { name: /tuesday\.mp4/ }));
    expect(fake.sendMessage).toHaveBeenCalledWith("c1", { body: "Look at this one", analysis_id: "mine1" });
    const card = await screen.findByRole("link", { name: /Open your serve from/ });
    expect(card).toHaveAttribute("href", "/analyses/mine1");
    expect(screen.getByLabelText("Message")).toHaveValue("");
  });

  it("say when a serve isn't available any more", async () => {
    fake.messages = [{ id: "m1", from_you: false, body: "Check this out", deleted: false, created_at: "2026-10-13T10:00:00Z",
      serve: { analysis_id: null, available: false, overall_score: null, recorded_at: null, thumbnail_url: null } }];
    renderAt("/messages/c1");
    expect(await screen.findByText("This serve isn't available any more.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Open their serve/ })).not.toBeInTheDocument();
  });
});

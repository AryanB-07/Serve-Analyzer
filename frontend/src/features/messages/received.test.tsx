/** Received serves: who sent what and when, new until opened, greyed out once you can't open it. */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ReceivedServe, ReceivedServePage } from "../../api/types";

const ANN = { username: "ann", display_name: "Ann A", avatar_url: null };
const BOB = { username: "bob", display_name: "Bob B", avatar_url: null };
const item = (id: string, sender: typeof ANN, seen: boolean, available = true): ReceivedServe => ({
  message_id: id, conversation_id: `c-${sender.username}`, sender, sent_at: "2026-10-13T09:00:00Z", seen,
  serve: available
    ? { analysis_id: `a-${id}`, available: true, overall_score: 81, recorded_at: "2026-10-12T09:00:00Z", thumbnail_url: "/t.jpg" }
    : { analysis_id: null, available: false, overall_score: null, recorded_at: null, thumbnail_url: null },
});

const fake = vi.hoisted(() => ({
  pages: [] as (ReceivedServePage | Error)[],
  listReceived: vi.fn(),
  countUnseenServes: vi.fn(),
  countUnread: vi.fn(async () => 0),
  listConversations: vi.fn(async () => []),
}));
vi.mock("../../api", async () => {
  const client = await import("../../api/client");
  return { api: fake, USE_MOCKS: false, ApiError: client.ApiError, UploadAbortedError: client.UploadAbortedError };
});

const { ApiError } = await import("../../api/client");
const { createQueryClient } = await import("../../api/session");
const { ReceivedPage } = await import("./ReceivedPage");
const { MessagesPage } = await import("./MessagesPage");

beforeEach(() => {
  fake.pages = [
    { items: [item("m3", ANN, false), item("m2", BOB, true)], next_cursor: "next" },
    { items: [item("m1", ANN, false, false)], next_cursor: null },
  ];
  fake.listReceived.mockReset().mockImplementation(async (cursor?: string) => {
    const page = fake.pages[cursor ? 1 : 0]!;
    if (page instanceof Error) throw page;
    return page;
  });
  fake.countUnseenServes.mockReset().mockResolvedValue(1);
});

function renderAt(path: string) {
  const router = createMemoryRouter([
    { path: "/messages", element: <MessagesPage /> },
    { path: "/messages/received", element: <ReceivedPage /> },
    { path: "/analyses/:id", element: <h1>A serve</h1> },
  ], { initialEntries: [path] });
  render(<QueryClientProvider client={createQueryClient()}><RouterProvider router={router} /></QueryClientProvider>);
  return router;
}

const rows = () => within(screen.getByRole("list", { name: "Received serves" })).getAllByRole("listitem");

describe("received serves", () => {
  it("say who sent each one and when, newest first, with the new ones marked", async () => {
    renderAt("/messages/received");
    await screen.findByRole("list", { name: "Received serves" });
    const [first, second] = rows();
    expect(first).toHaveTextContent("Ann A sent you a serve");
    expect(within(first!).getByText("New")).toBeInTheDocument();
    expect(within(first!).getByRole("link", { name: /^Open their serve/ })).toHaveAttribute("href", "/analyses/a-m3");
    expect(within(first!).getByRole("link", { name: "Open conversation" })).toHaveAttribute("href", "/messages/c-ann");
    expect(within(first!).getByRole("time")).toHaveAttribute("dateTime", "2026-10-13T09:00:00Z");
    expect(second).toHaveTextContent("Bob B sent you a serve");
    expect(within(second!).getByText("Seen")).toBeInTheDocument();
  });

  it("shows ones you can't open any more greyed out, not new", async () => {
    renderAt("/messages/received");
    await userEvent.click(await screen.findByRole("button", { name: "Load more" }));
    const gone = await screen.findByText("This serve isn't available any more.");
    const row = gone.closest("li")!;
    expect(row.className).toMatch(/opacity-75/);
    expect(within(row).queryByText("New")).not.toBeInTheDocument();
    expect(within(row).queryByRole("link", { name: /^Open their serve/ })).not.toBeInTheDocument();
    expect(fake.listReceived).toHaveBeenLastCalledWith("next");
  });

  it("badges the switch with how many are new, from either page", async () => {
    renderAt("/messages");
    const link = await screen.findByRole("link", { name: "Received serves, 1 new" });
    expect(link).toHaveAttribute("href", "/messages/received");
    expect(screen.getByRole("link", { name: "Conversations" })).toHaveAttribute("aria-current", "page");
    await userEvent.click(link);
    expect(await screen.findByRole("list", { name: "Received serves" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Received serves, 1 new" })).toHaveAttribute("aria-current", "page");
  });

  it("says when there are none", async () => {
    fake.pages = [{ items: [], next_cursor: null }];
    fake.countUnseenServes.mockResolvedValue(0);
    renderAt("/messages/received");
    expect(await screen.findByText("No serves yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Received serves" })).toBeInTheDocument();
  });

  it("offers to try again when the list can't load", async () => {
    fake.pages = [new ApiError(429, "Too many requests.")];
    renderAt("/messages/received");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("We couldn't load the serves sent to you.");
    fake.pages = [{ items: [item("m3", ANN, false)], next_cursor: null }];
    await userEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("list", { name: "Received serves" })).toHaveTextContent("Ann A sent you a serve");
  });
});

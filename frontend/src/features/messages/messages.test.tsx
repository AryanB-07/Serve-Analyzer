/** Messages: the list, a conversation, sending, deleting, reporting, and the navigation badge. */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
// The app's RouterProvider (main.tsx): only this one honours navigate()'s flushSync.
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ConversationSummary, Message, Person, Profile, User } from "../../api/types";

const ALICE: User = { id: "u1", email: "alice@example.com", created_at: "2026-03-02T10:00:00Z", email_verified: true };
const PROFILE: Profile = {
  username: "alice", display_name: "Alice", bio: null, avatar_url: null, member_since: ALICE.created_at,
  stats: { serves: 0, average_score: null, averaged_over: 0, best_score: null }, allow_follows: true,
  share_stats: false, share_positions: false, on_leaderboard: false,
};
const BOB = { username: "bob", display_name: "Bob B", avatar_url: null };
const CONV: ConversationSummary = {
  id: "c1", person: BOB, unread: 2, can_send: true, why_not: null,
  last_message: { text: "Hit on Saturday?", from_you: false, deleted: false, at: "2026-10-13T09:00:00Z" },
};
const msg = (id: string, from_you: boolean, body: string | null, at: string): Message =>
  ({ id, from_you, body, deleted: body === null, created_at: at });

const fake = vi.hoisted(() => ({
  listPostsBy: vi.fn(async () => ({ items: [], next_cursor: null })),
  conversations: [] as ConversationSummary[],
  conversation: null as unknown as ConversationSummary,
  messages: [] as Message[],
  seen: null as string | null,
  getMe: vi.fn(),
  getProfile: vi.fn(),
  countUnread: vi.fn(),
  countUnseenServes: vi.fn(async () => 0),
  listConversations: vi.fn(),
  getConversation: vi.fn(),
  listMessages: vi.fn(),
  sendMessage: vi.fn(),
  markRead: vi.fn(),
  deleteMessage: vi.fn(),
  report: vi.fn(),
  block: vi.fn(),
  getPerson: vi.fn(),
  startConversation: vi.fn(),
}));

vi.mock("../../api", async () => {
  const client = await import("../../api/client");
  return { api: fake, USE_MOCKS: false, ApiError: client.ApiError, UploadAbortedError: client.UploadAbortedError };
});

const { ApiError } = await import("../../api/client");
const { createQueryClient } = await import("../../api/session");
const { AppShell } = await import("../../components/AppShell");
const { PersonPage } = await import("../friends/PersonPage");
const { ConversationPage } = await import("./ConversationPage");
const { MessagesPage } = await import("./MessagesPage");

beforeEach(() => {
  fake.conversations = [CONV];
  fake.conversation = CONV;
  fake.messages = [
    msg("m3", false, "Hit on Saturday?", "2026-10-13T09:00:00Z"),
    msg("m2", true, "Thanks! Still working on the toss.", "2026-10-12T18:05:00Z"),
    msg("m1", false, "Your knee bend looks deeper!", "2026-10-12T18:00:00Z"),
  ];
  fake.seen = null;
  fake.getMe.mockReset().mockResolvedValue(ALICE);
  fake.getProfile.mockReset().mockResolvedValue(PROFILE);
  fake.countUnread.mockReset().mockImplementation(async () => fake.conversations.reduce((n, c) => n + c.unread, 0));
  fake.listConversations.mockReset().mockImplementation(async () => fake.conversations);
  fake.getConversation.mockReset().mockImplementation(async () => fake.conversation);
  fake.listMessages.mockReset().mockImplementation(async () => ({ items: fake.messages, next_cursor: null, seen_up_to: fake.seen }));
  fake.sendMessage.mockReset().mockImplementation(async (_id: string, { body }: { body: string }) => {
    const m = msg(`m${fake.messages.length + 1}`, true, body, "2026-10-14T10:00:00Z");
    fake.messages = [m, ...fake.messages];
    return m;
  });
  fake.markRead.mockReset().mockResolvedValue(undefined);
  fake.deleteMessage.mockReset().mockImplementation(async (id: string) => {
    fake.messages = fake.messages.map((m) => (m.id === id ? { ...m, body: null, deleted: true } : m));
  });
  fake.report.mockReset().mockResolvedValue(undefined);
  fake.block.mockReset().mockResolvedValue(undefined);
  fake.getPerson.mockReset().mockResolvedValue({ ...BOB, relationship: "friends", can_follow: false, counts: { followers: 3, following: 2, friends: 1 }, can_see_lists: false, bio: null,
    friends_since: "2026-09-01T10:00:00Z", stats: null, positions: null } satisfies Person);
  fake.startConversation.mockReset().mockResolvedValue(CONV);
});

function renderAt(path: string) {
  const router = createMemoryRouter(
    [{
      element: <AppShell />,
      children: [
        { path: "/messages", element: <MessagesPage /> },
        { path: "/messages/:id", element: <ConversationPage /> },
        { path: "/u/:username", element: <PersonPage /> },
        { path: "/", element: <h1>Upload page</h1> },
      ],
    }],
    { initialEntries: [path] },
  );
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

describe("the Messages list", () => {
  it("shows each conversation with its latest message and unread count", async () => {
    renderAt("/messages");
    const link = await screen.findByRole("link", { name: /Bob B/ });
    expect(link).toHaveAttribute("href", "/messages/c1");
    expect(within(link).getByText("Hit on Saturday?")).toBeInTheDocument();
    expect(within(link).getByText("unread", { exact: false })).toBeInTheDocument();
  });

  it("marks your own, deleted, and deleted-account conversations", async () => {
    fake.conversations = [
      { ...CONV, unread: 0, last_message: { text: "See you", from_you: true, deleted: false, at: "2026-10-13T09:00:00Z" } },
      { ...CONV, id: "c2", unread: 0, person: null, can_send: false, why_not: "They've deleted their account.",
        last_message: { text: null, from_you: false, deleted: true, at: "2026-10-01T09:00:00Z" } },
    ];
    renderAt("/messages");
    expect(await screen.findByText("You: See you")).toBeInTheDocument();
    expect(screen.getByText("Deleted account")).toBeInTheDocument();
    expect(screen.getByText("Message deleted")).toBeInTheDocument();
  });

  it("has an empty state that points to Friends", async () => {
    fake.conversations = [];
    renderAt("/messages");
    expect(await screen.findByText("No messages yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to Friends" })).toHaveAttribute("href", "/friends");
  });
});

describe("a conversation", () => {
  it("shows messages oldest first and marks them read", async () => {
    renderAt("/messages/c1");
    const thread = await screen.findByRole("region", { name: "Messages with Bob B" });
    const items = within(thread).getAllByRole("listitem");
    expect(items.map((li) => li.textContent)).toEqual([
      expect.stringContaining("Your knee bend looks deeper!"),
      expect.stringContaining("Still working on the toss."),
      expect.stringContaining("Hit on Saturday?"),
    ]);
    await vi.waitFor(() => expect(fake.markRead).toHaveBeenCalledWith("c1"));
  });

  it("shows Seen under your latest message once they've read it", async () => {
    fake.seen = "2026-10-12T18:06:00Z";
    renderAt("/messages/c1");
    const thread = await screen.findByRole("region", { name: "Messages with Bob B" });
    expect(within(thread).getByText("Seen")).toBeInTheDocument();
  });

  it("sends with Enter and adds a line with Shift+Enter", async () => {
    renderAt("/messages/c1");
    const box = await screen.findByLabelText("Message");
    await userEvent.type(box, "Yes!{Shift>}{Enter}{/Shift}10am?");
    expect(box).toHaveValue("Yes!\n10am?");
    await userEvent.type(box, "{Enter}");
    expect(fake.sendMessage).toHaveBeenCalledWith("c1", { body: "Yes!\n10am?" });
    await vi.waitFor(() => expect(box).toHaveValue(""));
    expect(await screen.findByText(/10am\?/)).toBeInTheDocument();
  });

  it("won't send an empty or too-long message", async () => {
    renderAt("/messages/c1");
    const send = await screen.findByRole("button", { name: "Send" });
    expect(send).toBeDisabled();
    const box = screen.getByLabelText("Message");
    await userEvent.click(box);
    await userEvent.paste("x".repeat(2001));
    expect(send).toBeDisabled();
    expect(screen.getByText("2001/2000")).toBeInTheDocument();
  });

  it("deletes your own message for everyone after confirming", async () => {
    renderAt("/messages/c1");
    const thread = await screen.findByRole("region", { name: "Messages with Bob B" });
    await userEvent.click(within(thread).getByRole("button", { name: "Delete" }));
    expect(within(thread).getByText("Delete for everyone?")).toBeInTheDocument();
    await userEvent.click(within(thread).getByRole("button", { name: "Yes, delete it" }));
    expect(fake.deleteMessage).toHaveBeenCalledWith("m2");
    expect(await within(thread).findByText("Message deleted")).toBeInTheDocument();
  });

  it("reports one of their messages, and can block them too", async () => {
    renderAt("/messages/c1");
    const thread = await screen.findByRole("region", { name: "Messages with Bob B" });
    await userEvent.click(within(thread).getAllByRole("button", { name: "Report" })[1]!);
    const form = screen.getByRole("form", { name: "Report this message from Bob B" });
    const send = within(form).getByRole("button", { name: "Send report" });
    expect(send).toBeDisabled(); // a reason first
    await userEvent.click(within(form).getByLabelText("Harassment or bullying"));
    await userEvent.type(within(form).getByLabelText(/Anything to add/), "Not the first time");
    await userEvent.click(within(form).getByLabelText("Also block Bob B"));
    await userEvent.click(send);
    expect(fake.report).toHaveBeenCalledWith({ username: "bob", message_id: "m3", post_id: null, comment_id: null,
      reason: "harassment", note: "Not the first time" });
    expect(fake.block).toHaveBeenCalledWith("bob");
    expect(await screen.findByText(/you've blocked Bob B/)).toBeInTheDocument();
  });

  it("explains why you can't send after a friendship ends", async () => {
    fake.conversation = { ...CONV, can_send: false, why_not: "You're no longer friends." };
    renderAt("/messages/c1");
    expect(await screen.findByText(/You're no longer friends\. You can still read the conversation\./)).toBeInTheDocument();
    expect(screen.queryByLabelText("Message")).not.toBeInTheDocument();
  });

  it("shows the server's reason when a message can't be sent", async () => {
    fake.sendMessage.mockRejectedValueOnce(new ApiError(429, "Too many attempts. Try again later."));
    renderAt("/messages/c1");
    await userEvent.type(await screen.findByLabelText("Message"), "hi{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts");
    expect(screen.getByLabelText("Message")).toHaveValue("hi"); // not lost
  });

  it("says when the conversation can't be found (or there's a block)", async () => {
    fake.getConversation.mockRejectedValue(new ApiError(404, "Conversation not found"));
    fake.listMessages.mockRejectedValue(new ApiError(404, "Conversation not found"));
    renderAt("/messages/nope");
    expect(await screen.findByRole("heading", { name: "Conversation not found" })).toBeInTheDocument();
  });
});

describe("starting a conversation", () => {
  it("opens from a friend's page", async () => {
    const router = renderAt("/u/bob");
    await userEvent.click(await screen.findByRole("button", { name: "Message" }));
    expect(fake.startConversation).toHaveBeenCalledWith("bob");
    await vi.waitFor(() => expect(router.state.location.pathname).toBe("/messages/c1"));
  });

  it("reports a person from their page", async () => {
    renderAt("/u/bob");
    await userEvent.click(await screen.findByRole("button", { name: "Report Bob B…" }));
    const form = screen.getByRole("form", { name: "Report Bob B" });
    await userEvent.click(within(form).getByLabelText("Pretending to be someone else"));
    await userEvent.click(within(form).getByRole("button", { name: "Send report" }));
    expect(fake.report).toHaveBeenCalledWith({ username: "bob", message_id: null, post_id: null, comment_id: null,
      reason: "impersonation", note: null });
    expect(await screen.findByText(/We'll look at it/)).toBeInTheDocument();
  });
});

describe("the navigation", () => {
  it("has Messages with an unread badge", async () => {
    renderAt("/");
    expect(await screen.findByRole("link", { name: "Messages, 2 new messages" })).toHaveAttribute("href", "/messages");
  });
});

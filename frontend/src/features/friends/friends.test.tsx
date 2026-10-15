/** Friends: the list, requests, someone's page, blocking, the navigation badge and Settings' privacy. */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
// The app's RouterProvider (main.tsx): only this one honours navigate()'s flushSync.
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ConnectionList, Person, PersonSummary, Profile, User } from "../../api/types";

const ALICE: User = { id: "u1", email: "alice@example.com", created_at: "2026-03-02T10:00:00Z", email_verified: true };
const PROFILE: Profile = {
  username: "alice", display_name: "Alice", bio: null, avatar_url: null, member_since: ALICE.created_at,
  stats: { serves: 0, average_score: null, averaged_over: 0, best_score: null }, accept_requests: true,
};
const BOB = { username: "bob", display_name: "Bob B", avatar_url: null };
const CAROL = { username: "carol", display_name: null, avatar_url: null };

const fake = vi.hoisted(() => ({
  profile: null as unknown as Profile,
  list: null as unknown as ConnectionList,
  person: null as unknown as Person | Error,
  getMe: vi.fn(),
  logOut: vi.fn(),
  getProfile: vi.fn(),
  updateProfile: vi.fn(),
  listConnections: vi.fn(),
  countRequests: vi.fn(),
  getPerson: vi.fn(),
  sendRequest: vi.fn(),
  acceptRequest: vi.fn(),
  removeConnection: vi.fn(),
  listBlocks: vi.fn(),
  block: vi.fn(),
  unblock: vi.fn(),
  checkUsername: vi.fn(),
}));

vi.mock("../../api", async () => {
  const client = await import("../../api/client");
  return { api: fake, USE_MOCKS: false, ApiError: client.ApiError, UploadAbortedError: client.UploadAbortedError };
});

const { ApiError } = await import("../../api/client");
const { createQueryClient } = await import("../../api/session");
const { AppShell } = await import("../../components/AppShell");
const { SettingsPage } = await import("../account/AccountPages");
const { FriendsPage } = await import("./FriendsPage");
const { PersonPage } = await import("./PersonPage");

const pending = (id: string, person: PersonSummary, direction: "incoming" | "outgoing") => ({
  id, person, status: "pending" as const, direction, created_at: "2026-10-10T10:00:00Z", accepted_at: null,
});

beforeEach(() => {
  fake.profile = PROFILE;
  fake.list = { friends: [], incoming: [pending("c1", BOB, "incoming")], outgoing: [pending("c2", CAROL, "outgoing")] };
  fake.person = { ...BOB, relationship: "none", connection_id: null, can_request: true, bio: null, friends_since: null };
  fake.getMe.mockReset().mockResolvedValue(ALICE);
  fake.getProfile.mockReset().mockImplementation(async () => fake.profile);
  fake.updateProfile.mockReset().mockImplementation(async (body: Partial<Profile>) => (fake.profile = { ...fake.profile, ...body }));
  fake.listConnections.mockReset().mockImplementation(async () => fake.list);
  fake.countRequests.mockReset().mockImplementation(async () => fake.list.incoming.length);
  fake.getPerson.mockReset().mockImplementation(async () => {
    if (fake.person instanceof Error) throw fake.person;
    return fake.person;
  });
  fake.sendRequest.mockReset().mockImplementation(async () => {
    fake.person = { ...(fake.person as Person), relationship: "requested", connection_id: "c9", can_request: false };
    return fake.person;
  });
  fake.acceptRequest.mockReset().mockImplementation(async (id: string) => {
    const item = fake.list.incoming.find((c) => c.id === id)!;
    fake.list = { ...fake.list, incoming: fake.list.incoming.filter((c) => c.id !== id),
      friends: [{ ...item, status: "accepted", accepted_at: "2026-10-15T10:00:00Z" }] };
    return fake.list.friends[0];
  });
  fake.removeConnection.mockReset().mockImplementation(async (id: string) => {
    fake.list = { friends: fake.list.friends.filter((c) => c.id !== id), incoming: fake.list.incoming.filter((c) => c.id !== id),
      outgoing: fake.list.outgoing.filter((c) => c.id !== id) };
  });
  fake.listBlocks.mockReset().mockResolvedValue([]);
  fake.block.mockReset().mockImplementation(async () => {
    fake.person = new ApiError(404, "No one has that username.");
  });
  fake.unblock.mockReset().mockResolvedValue(undefined);
});

function renderAt(path: string) {
  const router = createMemoryRouter(
    [{
      element: <AppShell />,
      children: [
        { path: "/friends", element: <FriendsPage /> },
        { path: "/u/:username", element: <PersonPage /> },
        { path: "/settings", element: <SettingsPage /> },
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

describe("the Friends page", () => {
  it("lists requests, friends and sent requests", async () => {
    renderAt("/friends");
    const requests = await screen.findByRole("region", { name: /Requests/ });
    expect(within(requests).getByRole("link", { name: "Bob B" })).toHaveAttribute("href", "/u/bob");
    expect(screen.getByRole("region", { name: /Your friends/ })).toHaveTextContent("No friends yet");
    expect(within(screen.getByRole("region", { name: /Sent/ })).getByRole("link", { name: "@carol" })).toBeInTheDocument();
  });

  it("accepts and declines requests, and cancels sent ones", async () => {
    renderAt("/friends");
    await userEvent.click(await screen.findByRole("button", { name: "Accept Bob B's request" }));
    expect(fake.acceptRequest).toHaveBeenCalledWith("c1");
    const friends = await screen.findByRole("region", { name: /Your friends \(1\)/ });
    expect(within(friends).getByText(/Friends since/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /Requests/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel your request to @carol" }));
    expect(fake.removeConnection).toHaveBeenCalledWith("c2");
    await vi.waitFor(() => expect(screen.queryByRole("region", { name: /Sent/ })).not.toBeInTheDocument());
  });

  it("finds someone by username", async () => {
    const router = renderAt("/friends");
    const form = await screen.findByRole("form", { name: "Find someone" });
    await userEvent.type(within(form).getByLabelText(/username/), "ab");
    await userEvent.click(within(form).getByRole("button", { name: "Find" }));
    expect(within(form).getByRole("alert")).toHaveTextContent("3 to 20");
    await userEvent.clear(within(form).getByLabelText(/username/));
    await userEvent.type(within(form).getByLabelText(/username/), "@Bob");
    await userEvent.click(within(form).getByRole("button", { name: "Find" }));
    expect(router.state.location.pathname).toBe("/u/bob");
  });

  it("asks for a username first when you don't have one", async () => {
    fake.profile = { ...PROFILE, username: null };
    renderAt("/friends");
    expect(await screen.findByText("Choose a username to send friend requests")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Choose one in Settings" })).toHaveAttribute("href", "/settings#profile");
  });
});

describe("someone's page", () => {
  it("sends a friend request and can cancel it", async () => {
    renderAt("/u/bob");
    expect(await screen.findByRole("heading", { level: 1, name: "Bob B" })).toBeInTheDocument();
    expect(screen.getByText("@bob")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add friend" }));
    expect(fake.sendRequest).toHaveBeenCalledWith("bob");
    expect(await screen.findByText("Request sent.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel request" }));
    expect(fake.removeConnection).toHaveBeenCalledWith("c9");
  });

  it("shows a friend's bio, and asks before removing them", async () => {
    fake.person = { ...BOB, relationship: "friends", connection_id: "c5", can_request: false, bio: "Lefty.", friends_since: "2026-09-02T10:00:00Z" };
    renderAt("/u/bob");
    expect(await screen.findByText("Lefty.")).toBeInTheDocument();
    expect(screen.getByText(/^Friends since/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Remove friend…" }));
    expect(screen.getByText(/They won't be told/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Remove friend" }));
    expect(fake.removeConnection).toHaveBeenCalledWith("c5");
  });

  it("accepts a request from their page", async () => {
    fake.person = { ...BOB, relationship: "incoming", connection_id: "c1", can_request: false, bio: null, friends_since: null };
    renderAt("/u/bob");
    expect(await screen.findByText("Bob B wants to be friends.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect(fake.acceptRequest).toHaveBeenCalledWith("c1");
  });

  it("says when someone isn't accepting requests", async () => {
    fake.person = { ...BOB, relationship: "none", connection_id: null, can_request: false, bio: null, friends_since: null };
    renderAt("/u/bob");
    expect(await screen.findByText("Bob B isn't accepting friend requests.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add friend" })).not.toBeInTheDocument();
  });

  it("shows the server's reason when a request is refused", async () => {
    fake.sendRequest.mockRejectedValueOnce(new ApiError(409, "Choose a username first, so people know who's asking."));
    renderAt("/u/bob");
    await userEvent.click(await screen.findByRole("button", { name: "Add friend" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose a username first");
  });

  it("blocks after confirming, and says so instead of 'no one has that username'", async () => {
    renderAt("/u/bob");
    await userEvent.click(await screen.findByRole("button", { name: "Block Bob B…" }));
    expect(screen.getByText(/won't be told/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Block Bob B" }));
    expect(fake.block).toHaveBeenCalledWith("bob");
    expect(await screen.findByRole("heading", { name: "You've blocked Bob B" })).toBeInTheDocument();
    expect(screen.queryByText("No one has that username")).not.toBeInTheDocument();
  });

  it("explains a username nobody has", async () => {
    fake.person = new ApiError(404, "No one has that username.");
    renderAt("/u/ghost");
    expect(await screen.findByRole("heading", { name: "No one has that username" })).toBeInTheDocument();
    expect(screen.getByText("Check the spelling of @ghost.")).toBeInTheDocument();
    expect(fake.getPerson).toHaveBeenCalledTimes(1); // a 404 isn't retried
  });

  it("points you to your own profile", async () => {
    fake.person = { username: "alice", display_name: "Alice", avatar_url: null, relationship: "self", connection_id: null, can_request: false, bio: null, friends_since: null };
    renderAt("/u/alice");
    expect(await screen.findByRole("link", { name: "This is you: open your profile" })).toHaveAttribute("href", "/profile");
    expect(screen.queryByRole("button", { name: /Block/ })).not.toBeInTheDocument();
  });
});

describe("the navigation", () => {
  it("has Friends with a badge for waiting requests", async () => {
    renderAt("/");
    const link = await screen.findByRole("link", { name: "Friends, 1 new request" });
    expect(link).toHaveAttribute("href", "/friends");
  });

  it("has no badge when nothing is waiting", async () => {
    fake.list = { friends: [], incoming: [], outgoing: [] };
    renderAt("/");
    expect(await screen.findByRole("link", { name: "Friends" })).toBeInTheDocument();
  });
});

describe("Settings: friends and privacy", () => {
  it("turns friend requests off and on", async () => {
    renderAt("/settings");
    const toggle = await screen.findByRole("checkbox", { name: /Let people send me friend requests/ });
    expect(toggle).toBeChecked();
    await userEvent.click(toggle);
    expect(fake.updateProfile).toHaveBeenCalledWith({ accept_requests: false });
    expect(await screen.findByText(/Nobody can send you one/)).toBeInTheDocument();
  });

  it("lists blocked people and unblocks them", async () => {
    fake.listBlocks.mockResolvedValue([{ person: BOB, blocked_at: "2026-10-01T10:00:00Z" }]);
    renderAt("/settings");
    await userEvent.click(await screen.findByRole("button", { name: "Unblock Bob B" }));
    expect(fake.unblock).toHaveBeenCalledWith("bob");
  });
});

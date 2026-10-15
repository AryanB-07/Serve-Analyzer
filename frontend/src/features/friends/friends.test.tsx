/** Friends as mutual follows: the lists, someone's page, following, blocking, and Settings' privacy. */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
// The app's RouterProvider (main.tsx): only this one honours navigate()'s flushSync.
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { FollowCounts, FollowEntry, Person, PersonSummary, Profile, User } from "../../api/types";

type Lists = { counts: FollowCounts; friends: FollowEntry[]; followers: FollowEntry[]; following: FollowEntry[] };

const ALICE: User = { id: "u1", email: "alice@example.com", created_at: "2026-03-02T10:00:00Z", email_verified: true };
const PROFILE: Profile = {
  username: "alice", display_name: "Alice", bio: null, avatar_url: null, member_since: ALICE.created_at,
  stats: { serves: 0, average_score: null, averaged_over: 0, best_score: null }, allow_follows: true,
  share_stats: false, share_positions: false, on_leaderboard: false,
};
const BOB: PersonSummary = { username: "bob", display_name: "Bob B", avatar_url: null };
const CAROL: PersonSummary = { username: "carol", display_name: null, avatar_url: null };
const DAVE: PersonSummary = { username: "dave", display_name: "Dave D", avatar_url: null };
const COUNTS = { followers: 4, following: 3, friends: 2 };

const entry = (person: PersonSummary, you_follow: boolean, follows_you: boolean): FollowEntry =>
  ({ person, since: "2026-10-10T10:00:00Z", you_follow, follows_you });
const person = (relationship: Person["relationship"], extra: Partial<Person> = {}): Person =>
  ({ ...BOB, relationship, can_follow: relationship === "none" || relationship === "follows_you", counts: COUNTS,
    can_see_lists: relationship === "friends" || relationship === "self", bio: null, friends_since: null, stats: null,
    positions: null, ...extra });

const fake = vi.hoisted(() => ({
  listPostsBy: vi.fn(async () => ({ items: [], next_cursor: null })),
  profile: null as unknown as Profile,
  lists: null as unknown as Lists,
  pageSize: 100,
  person: null as unknown as Person | Error,
  getMe: vi.fn(),
  logOut: vi.fn(),
  getProfile: vi.fn(),
  updateProfile: vi.fn(),
  getFollowCounts: vi.fn(),
  listFollowPage: vi.fn(),
  getPerson: vi.fn(),
  follow: vi.fn(),
  unfollow: vi.fn(),
  removeFollower: vi.fn(),
  listBlocks: vi.fn(),
  block: vi.fn(),
  unblock: vi.fn(),
  checkUsername: vi.fn(),
  getLeaderboard: vi.fn(),
  startConversation: vi.fn(),
  countUnread: vi.fn(async () => 0),
  countNotifications: vi.fn(async () => 0),
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

beforeEach(() => {
  fake.profile = PROFILE;
  fake.lists = {
    counts: { friends: 1, followers: 2, following: 2 },
    friends: [entry(BOB, true, true)],
    followers: [entry(BOB, true, true), entry(CAROL, false, true)],
    following: [entry(BOB, true, true), entry(DAVE, true, false)],
  };
  fake.person = person("none");
  fake.getMe.mockReset().mockResolvedValue(ALICE);
  fake.getProfile.mockReset().mockImplementation(async () => fake.profile);
  fake.updateProfile.mockReset().mockImplementation(async (body: Partial<Profile>) => (fake.profile = { ...fake.profile, ...body }));
  fake.pageSize = 100;
  fake.getFollowCounts.mockReset().mockImplementation(async () => ({
    friends: fake.lists.friends.length, followers: fake.lists.followers.length, following: fake.lists.following.length }));
  fake.listFollowPage.mockReset().mockImplementation(async (_username: string, kind: keyof FollowCounts, cursor?: string) => {
    const all = fake.lists[kind];
    const start = cursor ? Number(cursor) : 0;
    const items = all.slice(start, start + fake.pageSize);
    return { items, next_cursor: start + fake.pageSize < all.length ? String(start + fake.pageSize) : null };
  });
  fake.getPerson.mockReset().mockImplementation(async () => {
    if (fake.person instanceof Error) throw fake.person;
    return fake.person;
  });
  fake.follow.mockReset().mockImplementation(async () => {
    const p = fake.person as Person;
    fake.person = { ...p, relationship: p.relationship === "follows_you" ? "friends" : "following", can_follow: false };
    return fake.person;
  });
  fake.unfollow.mockReset().mockImplementation(async (username: string) => {
    fake.lists = { ...fake.lists, friends: fake.lists.friends.filter((e) => e.person.username !== username),
      following: fake.lists.following.filter((e) => e.person.username !== username) };
  });
  fake.removeFollower.mockReset().mockImplementation(async (username: string) => {
    fake.lists = { ...fake.lists, followers: fake.lists.followers.filter((e) => e.person.username !== username) };
  });
  fake.listBlocks.mockReset().mockResolvedValue([]);
  fake.block.mockReset().mockImplementation(async () => {
    fake.person = new ApiError(404, "No one has that username.");
  });
  fake.unblock.mockReset().mockResolvedValue(undefined);
  fake.getLeaderboard.mockReset().mockResolvedValue({ window_days: 90, min_serves: 5, averaged_over: 10, you_are_on_it: false, ranked: [], not_ranked: [] });
  fake.startConversation.mockReset().mockResolvedValue({ id: "conv1", person: BOB, unread: 0, can_send: true, why_not: null, last_message: null });
});

function renderAt(path: string) {
  const router = createMemoryRouter(
    [{
      element: <AppShell />,
      children: [
        { path: "/friends", element: <FriendsPage /> },
        { path: "/u/:username", element: <PersonPage /> },
        { path: "/settings", element: <SettingsPage /> },
        { path: "/messages/:id", element: <h1>Conversation</h1> },
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

const tab = (name: RegExp) => screen.findByRole("tab", { name });

describe("the Friends page", () => {
  it("has friends, followers and following, with counts", async () => {
    renderAt("/friends");
    expect(await tab(/Friends 1/)).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /Followers 2/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Following 2/ })).toBeInTheDocument();
    const panel = screen.getByRole("tabpanel");
    expect(await within(panel).findByRole("link", { name: "Bob B" })).toHaveAttribute("href", "/u/bob");
    expect(within(panel).getByText(/Friends since/)).toBeInTheDocument();
  });

  it("follows a follower back, and removes one after confirming", async () => {
    renderAt("/friends");
    await userEvent.click(await tab(/Followers/));
    const panel = screen.getByRole("tabpanel");
    await within(panel).findByRole("link", { name: "@carol" });
    expect(within(panel).queryByRole("button", { name: "Follow Bob B back" })).not.toBeInTheDocument(); // already
    await userEvent.click(within(panel).getByRole("button", { name: "Follow @carol back" }));
    expect(fake.follow).toHaveBeenCalledWith("carol");
    await userEvent.click(within(panel).getByRole("button", { name: "Remove @carol from your followers" }));
    expect(within(panel).getByText(/They won't be told/)).toBeInTheDocument();
    await userEvent.click(within(panel).getByRole("button", { name: "Remove" }));
    expect(fake.removeFollower).toHaveBeenCalledWith("carol");
  });

  it("unfollows from Following, and unfriends from Friends, after confirming", async () => {
    renderAt("/friends");
    await userEvent.click(await tab(/Following/));
    await userEvent.click(within(screen.getByRole("tabpanel")).getByRole("button", { name: "Unfollow Dave D" }));
    await userEvent.click(within(screen.getByRole("tabpanel")).getByRole("button", { name: "Unfollow" }));
    expect(fake.unfollow).toHaveBeenCalledWith("dave");
    await userEvent.click(screen.getByRole("tab", { name: /Friends/ }));
    await userEvent.click(within(screen.getByRole("tabpanel")).getByRole("button", { name: "Unfriend Bob B" }));
    expect(screen.getByText(/You won't be friends any more/)).toBeInTheDocument();
    await userEvent.click(within(screen.getByRole("tabpanel")).getByRole("button", { name: "Unfollow" }));
    expect(fake.unfollow).toHaveBeenCalledWith("bob");
    expect(await within(screen.getByRole("tabpanel")).findByText(/No friends yet/)).toBeInTheDocument();
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
    expect(await screen.findByText("Choose a username to follow people")).toBeInTheDocument();
  });
});

describe("someone's page", () => {
  it("shows their counts, and a Follow button for a stranger", async () => {
    renderAt("/u/bob");
    expect(await screen.findByRole("heading", { level: 1, name: "Bob B" })).toBeInTheDocument();
    expect(screen.getByText("followers", { exact: false })).toHaveTextContent("4 followers");
    await userEvent.click(screen.getByRole("button", { name: "Follow" }));
    expect(fake.follow).toHaveBeenCalledWith("bob");
    expect(await screen.findByText(/You'll be friends if they follow you back/)).toBeInTheDocument();
  });

  it("offers Follow back to someone who follows you, which makes you friends", async () => {
    fake.person = person("follows_you");
    renderAt("/u/bob");
    expect(await screen.findByText("Bob B follows you. Follow back to be friends.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Follow back" }));
    expect(await screen.findByRole("button", { name: "Message" })).toBeInTheDocument();
  });

  it("lets you unfollow someone you follow", async () => {
    fake.person = person("following");
    renderAt("/u/bob");
    await userEvent.click(await screen.findByRole("button", { name: "Unfollow" }));
    expect(screen.getByText("Unfollow Bob B?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Unfollow" }));
    expect(fake.unfollow).toHaveBeenCalledWith("bob");
  });

  it("shows a friend's bio, messages them, and unfriends after confirming", async () => {
    fake.person = person("friends", { bio: "Lefty.", friends_since: "2026-09-02T10:00:00Z" });
    const router = renderAt("/u/bob");
    expect(await screen.findByText("Lefty.")).toBeInTheDocument();
    expect(screen.getByText(/^Friends since/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Unfriend…" }));
    expect(screen.getByText(/You won't be friends any more, and they won't be told/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await userEvent.click(screen.getByRole("button", { name: "Message" }));
    await vi.waitFor(() => expect(fake.startConversation).toHaveBeenCalledWith("bob"));
    await vi.waitFor(() => expect(router.state.location.pathname).toBe("/messages/conv1"));
  });

  it("says when someone isn't accepting new followers", async () => {
    fake.person = person("none", { can_follow: false });
    renderAt("/u/bob");
    expect(await screen.findByText("Bob B isn't accepting new followers.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Follow" })).not.toBeInTheDocument();
  });

  it("shows the server's reason when a follow is refused", async () => {
    fake.follow.mockRejectedValueOnce(new ApiError(409, "Choose a username first, so people can see who's following them."));
    renderAt("/u/bob");
    await userEvent.click(await screen.findByRole("button", { name: "Follow" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose a username first");
  });

  it("blocks after confirming, and says so instead of 'no one has that username'", async () => {
    renderAt("/u/bob");
    await userEvent.click(await screen.findByRole("button", { name: "Block Bob B…" }));
    expect(screen.getByText(/Neither of you will follow the other any more/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Block Bob B" }));
    expect(fake.block).toHaveBeenCalledWith("bob");
    expect(await screen.findByRole("heading", { name: "You've blocked Bob B" })).toBeInTheDocument();
  });

  it("explains a username nobody has", async () => {
    fake.person = new ApiError(404, "No one has that username.");
    renderAt("/u/ghost");
    expect(await screen.findByRole("heading", { name: "No one has that username" })).toBeInTheDocument();
    expect(fake.getPerson).toHaveBeenCalledTimes(1); // a 404 isn't retried
  });

  it("points you to your own profile", async () => {
    fake.person = { ...person("self"), username: "alice", display_name: "Alice" };
    renderAt("/u/alice");
    expect(await screen.findByRole("link", { name: "This is you: open your profile" })).toHaveAttribute("href", "/profile");
    expect(screen.queryByRole("button", { name: /Block/ })).not.toBeInTheDocument();
  });
});

describe("lists", () => {
  it("pages your lists with Load more", async () => {
    fake.pageSize = 1;
    renderAt("/friends");
    await userEvent.click(await tab(/Followers/));
    const panel = screen.getByRole("tabpanel");
    expect(await within(panel).findByRole("link", { name: "Bob B" })).toBeInTheDocument();
    expect(within(panel).queryByRole("link", { name: "@carol" })).not.toBeInTheDocument();
    await userEvent.click(within(panel).getByRole("button", { name: "Load more" }));
    expect(await within(panel).findByRole("link", { name: "@carol" })).toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
    expect(fake.listFollowPage).toHaveBeenLastCalledWith("alice", "followers", "1");
  });

  it("shows a friend's lists on their page, without actions", async () => {
    fake.person = person("friends", { friends_since: "2026-09-02T10:00:00Z" });
    renderAt("/u/bob");
    const lists = await screen.findByRole("region", { name: "Bob B's friends, followers and following" });
    expect(within(lists).getByRole("tab", { name: /Friends 2/ })).toBeInTheDocument(); // Bob's counts
    expect(await within(lists).findByText("Your friend")).toBeInTheDocument();
    expect(within(lists).queryByRole("button", { name: /Unfriend|Remove|Unfollow/ })).not.toBeInTheDocument();
    expect(fake.listFollowPage).toHaveBeenCalledWith("bob", "friends", undefined);
  });

  it("doesn't show the lists of someone who isn't a friend", async () => {
    fake.person = person("following");
    renderAt("/u/bob");
    await screen.findByRole("heading", { level: 1, name: "Bob B" });
    expect(screen.queryByRole("region", { name: /friends, followers and following/ })).not.toBeInTheDocument();
    expect(fake.listFollowPage).not.toHaveBeenCalled();
  });
});

describe("Settings: friends and privacy", () => {
  it("turns new followers off and on", async () => {
    renderAt("/settings");
    const toggle = await screen.findByRole("checkbox", { name: /Let people follow me/ });
    expect(toggle).toBeChecked();
    await userEvent.click(toggle);
    expect(fake.updateProfile).toHaveBeenCalledWith({ allow_follows: false });
    expect(await screen.findByText(/Only people you follow can follow you/)).toBeInTheDocument();
  });

  it("lists blocked people and unblocks them", async () => {
    fake.listBlocks.mockResolvedValue([{ person: BOB, blocked_at: "2026-10-01T10:00:00Z" }]);
    renderAt("/settings");
    await userEvent.click(await screen.findByRole("button", { name: "Unblock Bob B" }));
    expect(fake.unblock).toHaveBeenCalledWith("bob");
  });
});

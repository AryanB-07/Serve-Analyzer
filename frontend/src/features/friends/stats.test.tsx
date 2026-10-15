/** Friends' shared stats, the leaderboard, and the sharing switches in Settings. */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
// The app's RouterProvider (main.tsx): only this one honours navigate()'s flushSync.
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Leaderboard, Person, Profile, User } from "../../api/types";

const ALICE: User = { id: "u1", email: "alice@example.com", created_at: "2026-03-02T10:00:00Z", email_verified: true };
const PROFILE: Profile = {
  username: "alice", display_name: "Alice", bio: null, avatar_url: null, member_since: ALICE.created_at,
  stats: { serves: 12, average_score: 71, averaged_over: 10, best_score: 88 }, accept_requests: true,
  share_stats: false, share_positions: false, on_leaderboard: false,
};
const BOB_FRIEND: Person = {
  username: "bob", display_name: "Bob B", avatar_url: null, relationship: "friends", connection_id: "c1",
  can_request: false, bio: null, friends_since: "2026-09-02T10:00:00Z",
  stats: {
    serves: 14, average_score: 76, averaged_over: 10, best_score: 91, change: 6,
    trend: [55, 60, 64, 70, 76].map((score, i) => ({ at: `2026-10-0${i + 1}T10:00:00Z`, score })),
  },
  positions: {
    front_knee_flexion: { score: 84, measured: 10 }, back_knee_flexion: null, trunk_tilt: { score: 42, measured: 8 },
    elbow_angle: null, wrist_height: { score: 63, measured: 10 },
  },
};
const BOARD: Leaderboard = {
  window_days: 90, min_serves: 5, averaged_over: 10, you_are_on_it: true,
  ranked: [
    { rank: 1, person: { username: "bob", display_name: "Bob B", avatar_url: null }, is_you: false, average_score: 82, scored_serves: 9, needed: 0 },
    { rank: 2, person: { username: "alice", display_name: "Alice", avatar_url: null }, is_you: true, average_score: 71, scored_serves: 12, needed: 0 },
  ],
  not_ranked: [
    { rank: null, person: { username: "carol", display_name: null, avatar_url: null }, is_you: false, average_score: null, scored_serves: 3, needed: 2 },
  ],
};

const fake = vi.hoisted(() => ({
  profile: null as unknown as Profile,
  person: null as unknown as Person,
  board: null as unknown as Leaderboard,
  getMe: vi.fn(),
  getProfile: vi.fn(),
  updateProfile: vi.fn(),
  getPerson: vi.fn(),
  listConnections: vi.fn(),
  countRequests: vi.fn(),
  getLeaderboard: vi.fn(),
  listBlocks: vi.fn(),
  checkUsername: vi.fn(),
}));

vi.mock("../../api", async () => {
  const client = await import("../../api/client");
  return { api: fake, USE_MOCKS: false, ApiError: client.ApiError, UploadAbortedError: client.UploadAbortedError };
});

const { createQueryClient } = await import("../../api/session");
const { AppShell } = await import("../../components/AppShell");
const { SettingsPage } = await import("../account/AccountPages");
const { ProfilePage } = await import("../profile/ProfilePage");
const { FriendsPage } = await import("./FriendsPage");
const { PersonPage } = await import("./PersonPage");

beforeEach(() => {
  fake.profile = PROFILE;
  fake.person = BOB_FRIEND;
  fake.board = BOARD;
  fake.getMe.mockReset().mockResolvedValue(ALICE);
  fake.getProfile.mockReset().mockImplementation(async () => fake.profile);
  fake.updateProfile.mockReset().mockImplementation(async (body: Partial<Profile>) => (fake.profile = { ...fake.profile, ...body }));
  fake.getPerson.mockReset().mockImplementation(async () => fake.person);
  fake.listConnections.mockReset().mockResolvedValue({
    friends: [{ id: "c1", person: { username: "bob", display_name: "Bob B", avatar_url: null }, status: "accepted", direction: "outgoing",
      created_at: "2026-09-01T10:00:00Z", accepted_at: "2026-09-02T10:00:00Z" }],
    incoming: [], outgoing: [],
  });
  fake.countRequests.mockReset().mockResolvedValue(0);
  fake.getLeaderboard.mockReset().mockImplementation(async () => fake.board);
  fake.listBlocks.mockReset().mockResolvedValue([]);
});

function renderAt(path: string) {
  const router = createMemoryRouter(
    [{
      element: <AppShell />,
      children: [
        { path: "/friends", element: <FriendsPage /> },
        { path: "/u/:username", element: <PersonPage /> },
        { path: "/settings", element: <SettingsPage /> },
        { path: "/profile", element: <ProfilePage /> },
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

describe("a friend's serves", () => {
  it("shows what they share: stats, trend and key positions, with the ranges caveat", async () => {
    renderAt("/u/bob");
    const section = await screen.findByRole("region", { name: "Bob B's serves" });
    expect(within(section).getByText("14")).toBeInTheDocument();
    expect(within(section).getByText("76").className).toMatch(/text-warn/);
    expect(within(section).getByText("91").className).toMatch(/text-good/);
    expect(within(section).getByRole("img", { name: "Scores of Bob B's latest 5 serves, from 55 to 76" })).toBeInTheDocument();
    expect(within(section).getByText("+6")).toBeInTheDocument();
    expect(within(section).getByRole("meter", { name: "Trunk tilt average" })).toHaveAttribute("aria-valuenow", "42");
    expect(within(section).getAllByText("Not measured")).toHaveLength(2);
    expect(within(section).getByText(/haven't been validated yet/)).toBeInTheDocument();
  });

  it("shows only the stats when positions aren't shared", async () => {
    fake.person = { ...BOB_FRIEND, positions: null };
    renderAt("/u/bob");
    const section = await screen.findByRole("region", { name: "Bob B's serves" });
    expect(within(section).queryByText("Key positions")).not.toBeInTheDocument();
    expect(within(section).getByText("Best score")).toBeInTheDocument();
  });

  it("says when a friend shares nothing", async () => {
    fake.person = { ...BOB_FRIEND, stats: null, positions: null };
    renderAt("/u/bob");
    expect(await screen.findByText("Bob B isn't sharing serve stats with friends.")).toBeInTheDocument();
  });

  it("shows nothing about serves for someone who isn't a friend", async () => {
    fake.person = { ...BOB_FRIEND, relationship: "none", connection_id: null, can_request: true, stats: null, positions: null };
    renderAt("/u/bob");
    await screen.findByRole("button", { name: "Add friend" });
    expect(screen.queryByText(/serves/)).not.toBeInTheDocument();
  });
});

describe("the leaderboard", () => {
  it("ranks friends, highlights you, and says who still needs serves", async () => {
    renderAt("/friends");
    const board = await screen.findByRole("region", { name: "Leaderboard" });
    expect(within(board).getByText(/latest 10 scored serves from the last 90 days/)).toBeInTheDocument();
    const rows = within(board).getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(within(rows[0]!).getByLabelText("Rank 1")).toBeInTheDocument();
    expect(within(rows[0]!).getByRole("link", { name: "Bob B" })).toHaveAttribute("href", "/u/bob");
    expect(rows[1]).toHaveAttribute("aria-current", "true");
    expect(within(rows[1]!).getByText("Alice (you)")).toBeInTheDocument();
    expect(within(rows[2]!).getByLabelText("Not ranked")).toBeInTheDocument();
    expect(within(rows[2]!).getByText("2 more serves to be ranked")).toBeInTheDocument();
    expect(within(board).queryByText("Join from Settings")).not.toBeInTheDocument();
  });

  it("invites you to join when you're not on it", async () => {
    fake.board = { ...BOARD, you_are_on_it: false, ranked: [BOARD.ranked[0]!] };
    renderAt("/friends");
    const board = await screen.findByRole("region", { name: "Leaderboard" });
    expect(within(board).getByRole("link", { name: "Join from Settings" })).toHaveAttribute("href", "/settings#sharing");
  });
});

describe("choosing what friends see", () => {
  it("has each kind of sharing off until turned on", async () => {
    renderAt("/settings");
    const sharing = await screen.findByRole("group", { name: "What friends see" });
    for (const name of [/My serve stats/, /My key positions/, /Put me on the leaderboard/]) {
      expect(within(sharing).getByRole("checkbox", { name })).not.toBeChecked();
    }
    await userEvent.click(within(sharing).getByRole("checkbox", { name: /My serve stats/ }));
    expect(fake.updateProfile).toHaveBeenCalledWith({ share_stats: true });
    await vi.waitFor(() => expect(within(sharing).getByRole("checkbox", { name: /My serve stats/ })).toBeChecked());
  });

  it("says on your profile what friends can see", async () => {
    renderAt("/profile");
    expect(await screen.findByText(/Friends don't see your serve stats/)).toBeInTheDocument();
    fake.profile = { ...PROFILE, share_stats: true, on_leaderboard: true };
    renderAt("/profile");
    expect(await screen.findByText(/Friends see these stats, your place on the leaderboard/)).toBeInTheDocument();
  });
});

describe("switches while saving", () => {
  it("show the new value straight away, and go back if the save fails", async () => {
    let fail!: (e: Error) => void;
    fake.updateProfile.mockImplementationOnce(() => new Promise((_, reject) => (fail = reject)));
    renderAt("/settings");
    const stats = await screen.findByRole("checkbox", { name: /My serve stats/ });
    await userEvent.click(stats);
    expect(stats).toBeChecked(); // before the server answers
    fail(new Error("offline"));
    await vi.waitFor(() => expect(stats).not.toBeChecked());
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("don't get stuck when two are flipped quickly", async () => {
    renderAt("/settings");
    const stats = await screen.findByRole("checkbox", { name: /My serve stats/ });
    const board = screen.getByRole("checkbox", { name: /Put me on the leaderboard/ });
    await userEvent.click(stats);
    await userEvent.click(board);
    await vi.waitFor(() => expect(fake.updateProfile).toHaveBeenCalledTimes(2));
    await vi.waitFor(() => expect(stats).toBeChecked());
    expect(board).toBeChecked();
    expect(fake.profile.share_stats && fake.profile.on_leaderboard).toBe(true);
  });
});

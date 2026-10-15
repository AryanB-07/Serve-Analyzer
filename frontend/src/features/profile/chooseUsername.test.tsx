/** Accounts from before usernames were required choose one before anything else. */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Profile, User } from "../../api/types";

const ALICE: User = { id: "u1", email: "alice@example.com", created_at: "2026-03-02T10:00:00Z", email_verified: true };
const fake = vi.hoisted(() => ({
  profile: null as unknown as Profile,
  getMe: vi.fn(),
  getProfile: vi.fn(),
  updateProfile: vi.fn(),
  checkUsername: vi.fn(),
}));
vi.mock("../../api", async () => {
  const client = await import("../../api/client");
  return { api: fake, USE_MOCKS: false, ApiError: client.ApiError, UploadAbortedError: client.UploadAbortedError };
});

const { createQueryClient } = await import("../../api/session");
const { RequireAuth } = await import("../auth/RequireAuth");
const { ChooseUsernamePage } = await import("./ChooseUsernamePage");

beforeEach(() => {
  fake.profile = {
    username: null, display_name: null, bio: null, avatar_url: null, member_since: ALICE.created_at,
    stats: { serves: 0, average_score: null, averaged_over: 0, best_score: null }, allow_follows: true,
    share_stats: false, share_positions: false, on_leaderboard: false,
  };
  fake.getMe.mockReset().mockResolvedValue(ALICE);
  fake.getProfile.mockReset().mockImplementation(async () => fake.profile);
  fake.updateProfile.mockReset().mockImplementation(async (body: Partial<Profile>) => (fake.profile = { ...fake.profile, ...body }));
  fake.checkUsername.mockReset().mockImplementation(async (username: string) => ({ username, available: username !== "taken", problem: username === "taken" ? "That username is taken." : null }));
});

function renderAt(path: string) {
  const router = createMemoryRouter(
    [{ element: <RequireAuth />, children: [
      { path: "/serves", element: <h1>My Serves page</h1> },
      { path: "/choose-username", element: <ChooseUsernamePage /> },
    ] }],
    { initialEntries: [path] },
  );
  render(<QueryClientProvider client={createQueryClient()}><RouterProvider router={router} /></QueryClientProvider>);
  return router;
}

describe("choosing a username", () => {
  it("is asked for first, then you carry on where you were going", async () => {
    const router = renderAt("/serves");
    expect(await screen.findByRole("heading", { name: "Choose a username" })).toBeInTheDocument();
    expect(router.state.location.search).toBe("?next=%2Fserves");
    const box = screen.getByLabelText("Username");
    await userEvent.type(box, "taken");
    expect(await screen.findByText("That username is taken.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a username that's available.");
    await userEvent.clear(box);
    await userEvent.type(box, "Old_Timer");
    await screen.findByText("@old_timer is available.");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(fake.updateProfile).toHaveBeenCalledWith({ username: "old_timer" });
    expect(await screen.findByRole("heading", { name: "My Serves page" })).toBeInTheDocument();
  });

  it("isn't asked of an account that has one", async () => {
    fake.profile = { ...fake.profile, username: "alice" };
    renderAt("/serves");
    expect(await screen.findByRole("heading", { name: "My Serves page" })).toBeInTheDocument();
  });

  it("won't follow a ?next= off the site", async () => {
    const router = renderAt("/choose-username?next=//evil.example");
    await userEvent.type(await screen.findByLabelText("Username"), "safe_name");
    await screen.findByText("@safe_name is available.");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    await vi.waitFor(() => expect(router.state.location.pathname).not.toBe("/choose-username"));
    expect(router.state.location.pathname).toBe("/");
  });
});

/** The profile page, Settings' profile and password sections, and the header's account menu. */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
// The app's RouterProvider (main.tsx): only this one honours navigate()'s flushSync.
import { createMemoryRouter, Outlet } from "react-router";
import { RouterProvider } from "react-router/dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Profile, User } from "../../api/types";

const ALICE: User = { id: "u1", email: "alice@example.com", created_at: "2026-03-02T10:00:00Z", email_verified: true };
const EMPTY: Profile = {
  username: null, display_name: null, bio: null, avatar_url: null, member_since: ALICE.created_at,
  stats: { serves: 0, average_score: null, averaged_over: 0, best_score: null },
};

const fake = vi.hoisted(() => ({
  profile: null as unknown as Profile,
  getMe: vi.fn(),
  logOut: vi.fn(),
  getProfile: vi.fn(),
  updateProfile: vi.fn(),
  checkUsername: vi.fn(),
  setAvatar: vi.fn(),
  removeAvatar: vi.fn(),
  changePassword: vi.fn(),
  requestEmailChange: vi.fn(),
  exportData: vi.fn(),
  deleteAccount: vi.fn(),
  resendVerification: vi.fn(),
}));
const prepare = vi.hoisted(() => ({ prepareAvatar: vi.fn() }));

vi.mock("../../api", async () => {
  const client = await import("../../api/client");
  return { api: fake, USE_MOCKS: false, ApiError: client.ApiError, UploadAbortedError: client.UploadAbortedError };
});
vi.mock("../../lib/avatar", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  prepareAvatar: prepare.prepareAvatar,
}));

const { ApiError } = await import("../../api/client");
const { createQueryClient } = await import("../../api/session");
const { AppShell } = await import("../../components/AppShell");
const { AvatarFileError } = await import("../../lib/avatar");
const { SettingsPage } = await import("../account/AccountPages");
const { ProfilePage } = await import("./ProfilePage");

beforeEach(() => {
  fake.profile = EMPTY;
  fake.getMe.mockReset().mockResolvedValue(ALICE);
  fake.logOut.mockReset().mockResolvedValue(undefined);
  fake.getProfile.mockReset().mockImplementation(async () => fake.profile);
  fake.updateProfile.mockReset().mockImplementation(async (body: Partial<Profile>) => {
    fake.profile = {
      ...fake.profile,
      ...("username" in body ? { username: String(body.username).trim().toLowerCase() } : {}),
      ...("display_name" in body ? { display_name: body.display_name?.trim() || null } : {}),
      ...("bio" in body ? { bio: body.bio?.trim() || null } : {}),
    };
    return fake.profile;
  });
  fake.checkUsername.mockReset().mockImplementation(async (username: string) => (
    username === "taken"
      ? { username, available: false, problem: "That username is taken." }
      : { username, available: true, problem: null }));
  fake.setAvatar.mockReset().mockImplementation(async () => (fake.profile = { ...fake.profile, avatar_url: "/api/storage/a.jpg" }));
  fake.removeAvatar.mockReset().mockImplementation(async () => (fake.profile = { ...fake.profile, avatar_url: null }));
  fake.changePassword.mockReset().mockResolvedValue(undefined);
  prepare.prepareAvatar.mockReset().mockResolvedValue(new Blob(["jpeg"], { type: "image/jpeg" }));
});

function renderAt(path: string) {
  const router = createMemoryRouter(
    [{
      element: <AppShell />,
      children: [
        { path: "/profile", element: <ProfilePage /> },
        { path: "/settings", element: <SettingsPage /> },
        { path: "/serves", element: <h1>My Serves page</h1> },
        { path: "/", element: <h1>Upload page</h1> },
        { path: "/login", element: <h1>Sign in</h1> },
      ],
    }, { path: "*", element: <Outlet /> }],
    { initialEntries: [path] },
  );
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

describe("the profile page", () => {
  it("invites you to fill in an empty profile", async () => {
    renderAt("/profile");
    expect(await screen.findByRole("heading", { level: 1, name: "Your profile" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Choose a username" })).toHaveAttribute("href", "/settings#profile");
    expect(screen.getByText("No bio yet.")).toBeInTheDocument();
    expect(screen.getByText("Member since March 2026")).toBeInTheDocument();
    expect(screen.getByText("Only you can see your profile for now.")).toBeInTheDocument();
    expect(screen.getByText("Appears after your first scored serve.")).toBeInTheDocument();
  });

  it("shows the name, username, bio and serve stats, coloured by band", async () => {
    fake.profile = {
      ...EMPTY, username: "ace_server", display_name: "Aryan B", bio: "Lefty.\nWorking on my kick.",
      stats: { serves: 23, average_score: 74, averaged_over: 10, best_score: 91 },
    };
    renderAt("/profile");
    expect(await screen.findByRole("heading", { level: 1, name: "Aryan B" })).toBeInTheDocument();
    expect(screen.getByText("@ace_server")).toBeInTheDocument();
    expect(screen.getByText(/Working on my kick/)).toBeInTheDocument();
    expect(screen.getByText("23")).toBeInTheDocument();
    expect(screen.getByText("74").className).toMatch(/text-warn/);
    expect(screen.getByText("91").className).toMatch(/text-good/);
    expect(screen.getByText("Your latest 10 scored serves.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Choose a username" })).not.toBeInTheDocument();
  });

  it("uploads a chosen photo after preparing it, and removes it", async () => {
    renderAt("/profile");
    await screen.findByRole("button", { name: "Add a photo" });
    const file = new File(["photo"], "me.heic", { type: "image/heic" });
    await userEvent.upload(screen.getByTestId("avatar-input"), file);
    expect(prepare.prepareAvatar).toHaveBeenCalledWith(file);
    expect(fake.setAvatar).toHaveBeenCalledWith(expect.any(Blob));
    await userEvent.click(await screen.findByRole("button", { name: "Remove" }));
    expect(fake.removeAvatar).toHaveBeenCalled();
    expect(await screen.findByRole("button", { name: "Add a photo" })).toBeInTheDocument();
  });

  it("explains a photo that can't be used", async () => {
    prepare.prepareAvatar.mockRejectedValueOnce(new AvatarFileError("That picture is over 25 MB. Choose a smaller one."));
    renderAt("/profile");
    await userEvent.upload(await screen.findByTestId("avatar-input"), new File(["x"], "big.jpg", { type: "image/jpeg" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("over 25 MB");
    expect(fake.setAvatar).not.toHaveBeenCalled();

    fake.setAvatar.mockRejectedValueOnce(new ApiError(422, "That picture couldn't be read."));
    await userEvent.upload(screen.getByTestId("avatar-input"), new File(["x"], "odd.jpg", { type: "image/jpeg" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That picture couldn't be read.");
  });
});

describe("Settings: profile", () => {
  const form = () => screen.findByRole("form", { name: "Profile" });

  it("saves only what changed", async () => {
    fake.profile = { ...EMPTY, display_name: "Old Name", bio: "Keep me" };
    renderAt("/settings");
    const profile = await form();
    const save = within(profile).getByRole("button", { name: "Save profile" });
    expect(save).toBeDisabled(); // nothing changed yet
    const name = within(profile).getByLabelText("Display name");
    await userEvent.clear(name);
    await userEvent.type(name, "New Name");
    await userEvent.click(save);
    expect(fake.updateProfile).toHaveBeenCalledWith({ display_name: "New Name" });
    expect(await within(profile).findByRole("status")).toHaveTextContent("Profile saved.");
    expect(save).toBeDisabled();
  });

  it("checks a username as it's typed", async () => {
    renderAt("/settings");
    const profile = await form();
    const username = within(profile).getByLabelText("Username");
    await userEvent.type(username, "ab");
    expect(within(profile).getByText("Usernames are 3 to 20 characters.")).toBeInTheDocument();
    expect(within(profile).getByRole("button", { name: "Save profile" })).toBeDisabled();
    await userEvent.type(username, "-c");
    expect(within(profile).getByText("Use only letters, numbers and underscores.")).toBeInTheDocument();
    await userEvent.clear(username);
    await userEvent.type(username, "taken");
    expect(within(profile).getByRole("button", { name: "Save profile" })).toBeDisabled(); // until the API answers
    expect(await within(profile).findByText("That username is taken.", {}, { timeout: 2000 })).toBeInTheDocument();
    expect(within(profile).getByRole("button", { name: "Save profile" })).toBeDisabled();
    await userEvent.clear(username);
    await userEvent.type(username, "Ace_Server");
    expect(await within(profile).findByText("@ace_server is available.", {}, { timeout: 2000 })).toBeInTheDocument();
    expect(within(profile).getByRole("button", { name: "Save profile" })).toBeEnabled();
    expect(fake.checkUsername).toHaveBeenLastCalledWith("ace_server");
    await userEvent.click(within(profile).getByRole("button", { name: "Save profile" }));
    expect(fake.updateProfile).toHaveBeenCalledWith({ username: "Ace_Server" });
    expect(await within(profile).findByText("This is your username.")).toBeInTheDocument();
  });

  it("won't remove a username, and shows the server's reason for refusing one", async () => {
    fake.profile = { ...EMPTY, username: "ace" };
    renderAt("/settings");
    const profile = await form();
    const username = within(profile).getByLabelText("Username");
    await userEvent.clear(username);
    expect(within(profile).getByText("You can change your username, but not remove it.")).toBeInTheDocument();
    expect(within(profile).getByRole("button", { name: "Save profile" })).toBeDisabled();

    // Someone takes it between the check and the save: the server's answer is shown.
    fake.updateProfile.mockRejectedValueOnce(new ApiError(409, "That username is taken."));
    await userEvent.type(username, "someone");
    await within(profile).findByText("@someone is available.", {}, { timeout: 2000 });
    await userEvent.click(within(profile).getByRole("button", { name: "Save profile" }));
    expect(await within(profile).findByRole("alert")).toHaveTextContent("That username is taken.");
  });

  it("counts the bio's characters", async () => {
    renderAt("/settings");
    const profile = await form();
    await userEvent.type(within(profile).getByLabelText("Bio"), "Lefty");
    expect(within(profile).getByText("5/300")).toBeInTheDocument();
    expect(within(profile).getByLabelText("Bio")).toHaveAttribute("maxLength", "300");
  });
});

describe("Settings: password", () => {
  const form = () => screen.findByRole("form", { name: "Change your password" });

  it("changes the password and says other devices were signed out", async () => {
    renderAt("/settings");
    const password = await form();
    await userEvent.type(within(password).getByLabelText("Current password"), "old password");
    await userEvent.type(within(password).getByLabelText("New password"), "a new passphrase");
    await userEvent.click(within(password).getByRole("button", { name: "Change password" }));
    expect(fake.changePassword).toHaveBeenCalledWith("old password", "a new passphrase");
    expect(await within(password).findByRole("status")).toHaveTextContent("Every other device has been signed out.");
    expect(within(password).getByLabelText("Current password")).toHaveValue("");
  });

  it("checks the new password first, and shows a wrong current one", async () => {
    renderAt("/settings");
    const password = await form();
    const submit = within(password).getByRole("button", { name: "Change password" });
    await userEvent.type(within(password).getByLabelText("Current password"), "same password");
    await userEvent.type(within(password).getByLabelText("New password"), "short");
    await userEvent.click(submit);
    expect(within(password).getByRole("alert")).toHaveTextContent("at least 8 characters");
    await userEvent.clear(within(password).getByLabelText("New password"));
    await userEvent.type(within(password).getByLabelText("New password"), "same password");
    await userEvent.click(submit);
    expect(within(password).getByRole("alert")).toHaveTextContent("That's your current password.");
    expect(fake.changePassword).not.toHaveBeenCalled();

    fake.changePassword.mockRejectedValueOnce(new ApiError(403, "Incorrect password."));
    await userEvent.clear(within(password).getByLabelText("New password"));
    await userEvent.type(within(password).getByLabelText("New password"), "a different one");
    await userEvent.click(submit);
    expect(await within(password).findByRole("alert")).toHaveTextContent("Incorrect password.");
  });
});

describe("the account menu", () => {
  it("opens to Profile, Settings and Sign out, and closes on Escape", async () => {
    fake.profile = { ...EMPTY, display_name: "Aryan B" };
    const router = renderAt("/");
    const button = await screen.findByRole("button", { name: "Your account" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(await screen.findByText("Aryan B")).toBeInTheDocument();
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveFocus();

    await userEvent.click(button);
    await userEvent.click(screen.getByRole("link", { name: "Profile" }));
    expect(router.state.location.pathname).toBe("/profile");
    expect(button).toHaveAttribute("aria-expanded", "false"); // closes on navigating
  });

  it("closes on a click outside", async () => {
    renderAt("/");
    const button = await screen.findByRole("button", { name: "Your account" });
    await userEvent.click(button);
    await userEvent.click(screen.getByRole("heading", { name: "Upload page" }));
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("shows initials until there's a picture", async () => {
    fake.profile = { ...EMPTY, display_name: "Aryan Bhan" };
    renderAt("/");
    const button = await screen.findByRole("button", { name: "Your account" });
    expect(await within(button).findByText("AB")).toBeInTheDocument();
  });

  it("shows the picture once there is one", async () => {
    fake.profile = { ...EMPTY, display_name: "Aryan Bhan", avatar_url: "/api/storage/me.jpg" };
    renderAt("/");
    const button = await screen.findByRole("button", { name: "Your account" });
    await vi.waitFor(() => expect(button.querySelector("img")).toHaveAttribute("src", "/api/storage/me.jpg"));
    expect(within(button).queryByText("AB")).not.toBeInTheDocument();
  });

  it("has My Serves in the main navigation", async () => {
    renderAt("/");
    expect(await screen.findByRole("link", { name: "My Serves" })).toHaveAttribute("href", "/serves");
  });
});

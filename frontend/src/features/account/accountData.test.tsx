/** Changing your email and downloading your data, against a fake backend. */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
// The app's RouterProvider (main.tsx): only this one honours navigate()'s flushSync.
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DataExport, User } from "../../api/types";

const fake = vi.hoisted(() => ({
  user: null as User | null,
  getMe: vi.fn(),
  requestEmailChange: vi.fn(),
  confirmEmailChange: vi.fn(),
  exportData: vi.fn(),
  getProfile: vi.fn(async () => ({
    username: null, display_name: null, bio: null, avatar_url: null, member_since: "2026-09-27T10:00:00Z",
    stats: { serves: 0, average_score: null, averaged_over: 0, best_score: null },
  })),
}));

vi.mock("../../api", async () => {
  const client = await import("../../api/client");
  return { api: fake, USE_MOCKS: false, ApiError: client.ApiError, UploadAbortedError: client.UploadAbortedError };
});

const { ApiError } = await import("../../api/client");
const { createQueryClient, exportFilename } = await import("../../api/session");
const pages = await import("./AccountPages");

const ALICE: User = { id: "u1", email: "alice@example.com", created_at: "2026-09-27T10:00:00Z", email_verified: true };
const EXPORT: DataExport = {
  exported_at: "2026-10-12T09:30:00Z",
  links_expire_at: "2026-10-12T15:30:00Z",
  account: { email: ALICE.email, email_verified: true, created_at: ALICE.created_at },
  analyses: [
    { id: "a1", filename: "serve.mp4", hand: "right", status: "succeeded", created_at: "2026-10-01T10:00:00Z", files: {} },
    { id: "a2", filename: "two.mov", hand: "right", status: "failed", created_at: "2026-10-02T10:00:00Z", files: {} },
  ],
};

beforeEach(() => {
  fake.user = ALICE;
  fake.getMe.mockReset().mockImplementation(async () => fake.user);
  fake.requestEmailChange.mockReset().mockResolvedValue(undefined);
  fake.confirmEmailChange.mockReset().mockImplementation(async () => {
    if (fake.user) fake.user = { ...fake.user, email: "new@example.com" };
  });
  fake.exportData.mockReset().mockResolvedValue(EXPORT);
});

afterEach(() => vi.restoreAllMocks());

function renderAt(path: string) {
  const router = createMemoryRouter(
    [
      { path: "/settings", element: <pages.SettingsPage /> },
      { path: "/confirm-email", element: <pages.ConfirmEmailChangePage /> },
      { path: "/login", element: <h1>Sign in</h1> },
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

describe("changing your email", () => {
  it("sends a link to the new address and keeps the old one until it's opened", async () => {
    renderAt("/settings");
    await userEvent.click(await screen.findByRole("button", { name: "Change your email" }));
    const form = screen.getByRole("form", { name: "Change your email" });
    await userEvent.type(screen.getByLabelText("New email"), " New@Example.com ");
    await userEvent.type(within(form).getByLabelText("Current password"), "my password");
    await userEvent.click(screen.getByRole("button", { name: "Send confirmation link" }));
    expect(fake.requestEmailChange).toHaveBeenCalledWith("New@Example.com", "my password");
    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("We sent a link to New@Example.com");
    expect(status).toHaveTextContent("Until then you keep signing in with alice@example.com");
    expect(form).not.toBeInTheDocument();
  });

  it("checks the address and password before sending", async () => {
    renderAt("/settings");
    await userEvent.click(await screen.findByRole("button", { name: "Change your email" }));
    const send = screen.getByRole("button", { name: "Send confirmation link" });
    await userEvent.type(screen.getByLabelText("New email"), "nope");
    await userEvent.click(send);
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a valid email address.");
    await userEvent.clear(screen.getByLabelText("New email"));
    await userEvent.type(screen.getByLabelText("New email"), "ALICE@example.com");
    await userEvent.click(send);
    expect(screen.getByRole("alert")).toHaveTextContent("That's already your email.");
    await userEvent.clear(screen.getByLabelText("New email"));
    await userEvent.type(screen.getByLabelText("New email"), "new@example.com");
    await userEvent.click(send);
    expect(screen.getByRole("alert")).toHaveTextContent("Enter your current password.");
    expect(fake.requestEmailChange).not.toHaveBeenCalled();
  });

  it("shows the server's reason, such as a wrong password or a taken address", async () => {
    fake.requestEmailChange.mockRejectedValue(new ApiError(409, "An account with this email already exists."));
    renderAt("/settings");
    await userEvent.click(await screen.findByRole("button", { name: "Change your email" }));
    const form = screen.getByRole("form", { name: "Change your email" });
    await userEvent.type(within(form).getByLabelText("New email"), "taken@example.com");
    await userEvent.type(within(form).getByLabelText("Current password"), "pw");
    await userEvent.click(screen.getByRole("button", { name: "Send confirmation link" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("An account with this email already exists.");
  });

  it("switches to the new address from the emailed link", async () => {
    renderAt("/confirm-email?token=tok");
    expect(await screen.findByRole("heading", { name: "Email changed" })).toBeInTheDocument();
    expect(fake.confirmEmailChange).toHaveBeenCalledTimes(1);
    expect(fake.confirmEmailChange).toHaveBeenCalledWith("tok");
    expect(await screen.findByText("new@example.com")).toBeInTheDocument();
  });

  it("works signed out, pointing to sign-in", async () => {
    fake.user = null;
    renderAt("/confirm-email?token=tok");
    expect(await screen.findByRole("heading", { name: "Email changed" })).toBeInTheDocument();
    expect(screen.getByText("Sign in with your new email address from now on.")).toBeInTheDocument();
  });

  it("says when the link has expired or the address was taken meanwhile", async () => {
    fake.confirmEmailChange.mockRejectedValue(new ApiError(409, "An account with this email already exists."));
    renderAt("/confirm-email?token=old");
    expect(await screen.findByRole("heading", { name: "We couldn't change your email" })).toBeInTheDocument();
    expect(screen.getByText("An account with this email already exists.")).toBeInTheDocument();
    expect(screen.getByText("Your account still uses its previous email address.")).toBeInTheDocument();
  });

  it("explains a link with no token", async () => {
    renderAt("/confirm-email");
    expect(await screen.findByText("This link is incomplete. Open it from the email again.")).toBeInTheDocument();
    expect(fake.confirmEmailChange).not.toHaveBeenCalled();
  });
});

describe("downloading your data", () => {
  it("saves the export as a dated JSON file", async () => {
    const createUrl = vi.fn(() => "blob:export");
    Object.assign(URL, { createObjectURL: createUrl, revokeObjectURL: vi.fn() });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      expect(this.download).toBe("serve-analyzer-data-2026-10-12.json");
      expect(this.href).toBe("blob:export");
    });
    renderAt("/settings");
    await userEvent.click(await screen.findByRole("button", { name: "Download my data" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Downloaded 2 analyses.");
    expect(click).toHaveBeenCalledTimes(1);
    const blob = (createUrl.mock.calls[0] as unknown as [Blob])[0];
    expect(blob.type).toBe("application/json");
    expect(JSON.parse(await blob.text())).toEqual(EXPORT);
  });

  it("shows why an export failed", async () => {
    fake.exportData.mockRejectedValue(new ApiError(429, "Too many attempts. Try again later."));
    renderAt("/settings");
    await userEvent.click(await screen.findByRole("button", { name: "Download my data" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts. Try again later.");
  });

  it("names the file after the export date", () => {
    expect(exportFilename("2026-01-05T23:59:59Z")).toBe("serve-analyzer-data-2026-01-05.json");
  });
});

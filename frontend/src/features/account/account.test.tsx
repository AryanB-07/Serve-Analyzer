/** Password reset, email verification, account deletion and deleting analyses, against a fake backend. */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { User } from "../../api/types";

const fake = vi.hoisted(() => ({
  user: null as User | null,
  getMe: vi.fn(),
  logIn: vi.fn(),
  signUp: vi.fn(),
  logOut: vi.fn(),
  verifyEmail: vi.fn(),
  resendVerification: vi.fn(),
  requestPasswordReset: vi.fn(),
  resetPassword: vi.fn(),
  deleteAccount: vi.fn(),
  deleteAnalysis: vi.fn(),
}));

vi.mock("../../api", async () => {
  const client = await import("../../api/client");
  return { api: fake, USE_MOCKS: false, ApiError: client.ApiError, UploadAbortedError: client.UploadAbortedError };
});

const { ApiError } = await import("../../api/client");
const { createQueryClient } = await import("../../api/session");
const { AppShell } = await import("../../components/AppShell");
const { DeleteAnalysisButton } = await import("../../components/DeleteAnalysisButton");
const { LoginPage } = await import("../auth/AuthPages");
const { RequireAuth } = await import("../auth/RequireAuth");
const { uploadErrorText } = await import("../upload/uploadError");
const pages = await import("./AccountPages");

const ALICE: User = { id: "u1", email: "alice@example.com", created_at: "2026-09-27T10:00:00Z", email_verified: true };
const EXPIRED = "This link is invalid or has expired. Request a new one.";

beforeEach(() => {
  fake.user = null;
  fake.getMe.mockReset().mockImplementation(async () => fake.user);
  fake.verifyEmail.mockReset().mockImplementation(async () => {
    if (fake.user) fake.user = { ...fake.user, email_verified: true };
  });
  fake.resendVerification.mockReset().mockResolvedValue(undefined);
  fake.requestPasswordReset.mockReset().mockResolvedValue(undefined);
  fake.resetPassword.mockReset().mockResolvedValue(undefined);
  fake.deleteAccount.mockReset().mockImplementation(async () => {
    fake.user = null;
  });
  fake.deleteAnalysis.mockReset().mockResolvedValue(undefined);
});

function renderApp(path: string) {
  const queryClient = createQueryClient();
  const router = createMemoryRouter(
    [
      {
        element: <AppShell />,
        children: [
          { path: "/login", element: <LoginPage /> },
          { path: "/forgot-password", element: <pages.ForgotPasswordPage /> },
          { path: "/reset-password", element: <pages.ResetPasswordPage /> },
          { path: "/verify-email", element: <pages.VerifyEmailPage /> },
          { path: "/account-deleted", element: <pages.AccountDeletedPage /> },
          {
            element: <RequireAuth />,
            children: [
              { path: "/", element: <><pages.VerifyEmailBanner /><h1>Upload page</h1></> },
              { path: "/account", element: <pages.AccountPage /> },
              {
                path: "/history",
                element: <DeleteAnalysisButton id="a1" filename="serve.mp4" onDeleted={() => router.navigate("/")} />,
              },
            ],
          },
        ],
      },
    ],
    { initialEntries: [path] },
  );
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

describe("password reset", () => {
  it("is linked from the sign-in page", async () => {
    const router = renderApp("/login");
    await userEvent.click(await screen.findByRole("link", { name: "Forgot your password?" }));
    expect(router.state.location.pathname).toBe("/forgot-password");
  });

  it("asks for a link and says the same thing whether or not the account exists", async () => {
    renderApp("/forgot-password");
    await userEvent.type(await screen.findByLabelText("Email"), "  someone@example.com ");
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByRole("heading", { name: "Check your email" })).toBeInTheDocument();
    expect(fake.requestPasswordReset).toHaveBeenCalledWith("someone@example.com");
    expect(screen.getByRole("status")).toHaveTextContent("If someone@example.com has an account, we've sent it a link");
  });

  it("checks the email before sending", async () => {
    renderApp("/forgot-password");
    await userEvent.type(await screen.findByLabelText("Email"), "not-an-email");
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a valid email address.");
    expect(fake.requestPasswordReset).not.toHaveBeenCalled();
  });

  it("sets a new password from the link's token", async () => {
    renderApp("/reset-password?token=abc123");
    const input = await screen.findByLabelText("New password");
    await userEvent.type(input, "short");
    await userEvent.click(screen.getByRole("button", { name: "Set new password" }));
    expect(screen.getByRole("alert")).toHaveTextContent("at least 8 characters");
    await userEvent.clear(input);
    await userEvent.type(input, "a much longer password");
    await userEvent.click(screen.getByRole("button", { name: "Set new password" }));
    expect(await screen.findByRole("heading", { name: "Password changed" })).toBeInTheDocument();
    expect(fake.resetPassword).toHaveBeenCalledWith("abc123", "a much longer password");
  });

  it("offers a new link when the old one has expired", async () => {
    fake.resetPassword.mockRejectedValue(new ApiError(400, EXPIRED));
    renderApp("/reset-password?token=old");
    await userEvent.type(await screen.findByLabelText("New password"), "a much longer password");
    await userEvent.click(screen.getByRole("button", { name: "Set new password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(EXPIRED);
    expect(screen.getByRole("link", { name: "Request a new link" })).toHaveAttribute("href", "/forgot-password");
  });

  it("explains a link with no token", async () => {
    renderApp("/reset-password");
    expect(await screen.findByRole("heading", { name: "This link is incomplete" })).toBeInTheDocument();
  });
});

describe("email verification", () => {
  it("confirms the address from the link, once", async () => {
    fake.user = { ...ALICE, email_verified: false };
    renderApp("/verify-email?token=tok");
    expect(await screen.findByRole("heading", { name: "Email confirmed" })).toBeInTheDocument();
    expect(fake.verifyEmail).toHaveBeenCalledTimes(1);
    expect(fake.verifyEmail).toHaveBeenCalledWith("tok");
  });

  it("says when a link has expired", async () => {
    fake.verifyEmail.mockRejectedValue(new ApiError(400, EXPIRED));
    renderApp("/verify-email?token=old");
    expect(await screen.findByRole("heading", { name: "We couldn't confirm your email" })).toBeInTheDocument();
    expect(screen.getByText(EXPIRED)).toBeInTheDocument();
  });

  it("shows a banner with a resend button until the email is confirmed", async () => {
    fake.user = { ...ALICE, email_verified: false };
    renderApp("/");
    const banner = await screen.findByRole("region", { name: "Confirm your email" });
    expect(banner).toHaveTextContent("alice@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Resend link" }));
    expect(await screen.findByText("New link sent.")).toBeInTheDocument();
    expect(fake.resendVerification).toHaveBeenCalledTimes(1);
  });

  it("shows no banner once confirmed", async () => {
    fake.user = ALICE;
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Upload page" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Confirm your email" })).not.toBeInTheDocument();
  });

  it("explains a refused upload from an unconfirmed account", () => {
    const text = uploadErrorText(new ApiError(403, "Confirm your email address to analyze serves."));
    expect(text.title).toBe("Confirm your email first.");
  });
});

describe("deleting the account", () => {
  it("needs the password and DELETE typed out, then signs out", async () => {
    fake.user = ALICE;
    const router = renderApp("/account");
    await userEvent.click(await screen.findByRole("button", { name: "Delete my account…" }));
    const submit = screen.getByRole("button", { name: "Permanently delete account" });
    await userEvent.type(screen.getByLabelText("Your password"), "secret password");
    expect(submit).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/to confirm/), "delete");
    expect(submit).toBeEnabled();
    await userEvent.click(submit);
    expect(await screen.findByRole("heading", { name: "Account deleted" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/account-deleted");
    expect(fake.deleteAccount).toHaveBeenCalledWith("secret password");
    expect(screen.queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
  });

  it("shows a wrong password and stays signed in", async () => {
    fake.user = ALICE;
    fake.deleteAccount.mockRejectedValue(new ApiError(403, "Incorrect password."));
    renderApp("/account");
    await userEvent.click(await screen.findByRole("button", { name: "Delete my account…" }));
    await userEvent.type(screen.getByLabelText("Your password"), "wrong");
    await userEvent.type(screen.getByLabelText(/to confirm/), "DELETE");
    await userEvent.click(screen.getByRole("button", { name: "Permanently delete account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect password.");
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });

  it("is reachable from the header", async () => {
    fake.user = ALICE;
    const router = renderApp("/");
    await userEvent.click(await screen.findByRole("link", { name: /alice@example.com/ }));
    expect(router.state.location.pathname).toBe("/account");
    expect(await screen.findByText(/confirmed/)).toBeInTheDocument();
  });
});

describe("deleting an analysis", () => {
  it("asks first, then deletes and moves on", async () => {
    fake.user = ALICE;
    const router = renderApp("/history");
    await userEvent.click(await screen.findByRole("button", { name: "Delete serve.mp4" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(fake.deleteAnalysis).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Delete serve.mp4" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
    expect(fake.deleteAnalysis).toHaveBeenCalledWith("a1");
  });

  it("shows why a deletion failed", async () => {
    fake.user = ALICE;
    fake.deleteAnalysis.mockRejectedValue(new ApiError(404, "Analysis not found"));
    renderApp("/history");
    await userEvent.click(await screen.findByRole("button", { name: "Delete serve.mp4" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't delete it: Analysis not found");
  });
});

/** Sign-in pages, the route guard and the header's account controls, against a fake backend. */
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
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
}));

vi.mock("../../api", async () => {
  const client = await import("../../api/client");
  return { api: fake, USE_MOCKS: false, ApiError: client.ApiError, UploadAbortedError: client.UploadAbortedError };
});

const { ApiError } = await import("../../api/client");
const { createQueryClient, sessionKey } = await import("../../api/session");
const { AppShell } = await import("../../components/AppShell");
const { LoginPage, SignupPage } = await import("./AuthPages");
const { RequireAuth } = await import("./RequireAuth");

const ALICE: User = { id: "u1", email: "alice@example.com", created_at: "2026-09-27T10:00:00Z", email_verified: true };

beforeEach(() => {
  fake.user = null;
  fake.getMe.mockReset().mockImplementation(async () => fake.user);
  fake.logIn.mockReset().mockImplementation(async ({ email }: { email: string }) => {
    fake.user = { ...ALICE, email };
    return fake.user;
  });
  fake.signUp.mockReset().mockImplementation(async ({ email }: { email: string }) => {
    fake.user = { ...ALICE, email };
    return fake.user;
  });
  fake.logOut.mockReset().mockImplementation(async () => {
    fake.user = null;
  });
});

function renderApp(path: string): { router: ReturnType<typeof createMemoryRouter>; queryClient: QueryClient } {
  const queryClient = createQueryClient();
  const router = createMemoryRouter(
    [
      {
        element: <AppShell />,
        children: [
          { path: "/login", element: <LoginPage /> },
          { path: "/signup", element: <SignupPage /> },
          {
            element: <RequireAuth />,
            children: [
              { path: "/", element: <h1>Upload page</h1> },
              { path: "/history", element: <h1>History page</h1> },
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
  return { router, queryClient };
}

const where = (router: ReturnType<typeof createMemoryRouter>) =>
  router.state.location.pathname + router.state.location.search;

async function fillAndSubmit(email: string, password: string, button: RegExp) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: button }));
}

describe("route guard", () => {
  it("sends signed-out visitors to sign in, remembering where they were going", async () => {
    const { router } = renderApp("/history");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(where(router)).toBe("/login?next=%2Fhistory");
    expect(screen.queryByRole("navigation", { name: "Main" })).not.toBeInTheDocument();
  });

  it("shows protected pages and the account controls when signed in", async () => {
    fake.user = ALICE;
    renderApp("/history");
    expect(await screen.findByRole("heading", { name: "History page" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
  });

  it("offers a retry when the server can't be reached", async () => {
    fake.getMe.mockRejectedValue(new TypeError("Failed to fetch"));
    renderApp("/");
    expect(await screen.findByRole("alert", {}, { timeout: 3000 })).toHaveTextContent("couldn't reach the server");
    fake.getMe.mockImplementation(async () => ALICE);
    await userEvent.setup().click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "Upload page" })).toBeInTheDocument();
  });

  it("returns to sign-in, then back, when the session expires mid-visit", async () => {
    fake.user = ALICE;
    const { router, queryClient } = renderApp("/history");
    await screen.findByRole("heading", { name: "History page" });
    act(() => queryClient.setQueryData(sessionKey, null)); // what a 401 on any data request does
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(where(router)).toBe("/login?next=%2Fhistory");
    await fillAndSubmit("alice@example.com", "correct horse", /sign in/i);
    expect(await screen.findByRole("heading", { name: "History page" })).toBeInTheDocument();
  });
});

describe("sign in", () => {
  it("signs in and continues to the page that was asked for", async () => {
    const { router } = renderApp("/login?next=%2Fhistory");
    await screen.findByRole("heading", { name: "Sign in" });
    await fillAndSubmit("alice@example.com", "correct horse", /sign in/i);
    expect(await screen.findByRole("heading", { name: "History page" })).toBeInTheDocument();
    expect(where(router)).toBe("/history");
    expect(fake.logIn).toHaveBeenCalledWith({ email: "alice@example.com", password: "correct horse" });
  });

  it("shows the server's message for a wrong password and stays put", async () => {
    fake.logIn.mockRejectedValue(new ApiError(401, "Incorrect email or password."));
    const { router } = renderApp("/login");
    await screen.findByRole("heading", { name: "Sign in" });
    await fillAndSubmit("alice@example.com", "wrong password", /sign in/i);
    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password.");
    expect(where(router)).toBe("/login");
  });

  it("explains rate limiting", async () => {
    fake.logIn.mockRejectedValue(new ApiError(429, "Too many attempts. Try again later."));
    renderApp("/login");
    await screen.findByRole("heading", { name: "Sign in" });
    await fillAndSubmit("alice@example.com", "whatever pw", /sign in/i);
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts");
  });

  it("ignores a ?next= that points off the site", async () => {
    const { router } = renderApp("/login?next=%2F%2Fevil.example");
    await screen.findByRole("heading", { name: "Sign in" });
    await fillAndSubmit("alice@example.com", "correct horse", /sign in/i);
    await screen.findByRole("heading", { name: "Upload page" });
    expect(where(router)).toBe("/");
  });

  it("checks the email before calling the server", async () => {
    renderApp("/login");
    await screen.findByRole("heading", { name: "Sign in" });
    await fillAndSubmit("not-an-email", "correct horse", /sign in/i);
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a valid email address.");
    expect(fake.logIn).not.toHaveBeenCalled();
  });

  it("sends someone already signed in straight on", async () => {
    fake.user = ALICE;
    const { router } = renderApp("/login?next=%2Fhistory");
    await screen.findByRole("heading", { name: "History page" });
    expect(where(router)).toBe("/history");
  });
});

describe("sign up", () => {
  it("requires 8 characters before calling the server", async () => {
    renderApp("/signup");
    await screen.findByRole("heading", { name: "Create your account" });
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "new-password");
    await fillAndSubmit("new@example.com", "short", /create account/i);
    expect(screen.getByRole("alert")).toHaveTextContent("at least 8 characters");
    expect(fake.signUp).not.toHaveBeenCalled();
  });

  it("creates the account and signs in", async () => {
    renderApp("/signup");
    await screen.findByRole("heading", { name: "Create your account" });
    await fillAndSubmit("new@example.com", "long enough", /create account/i);
    expect(await screen.findByRole("heading", { name: "Upload page" })).toBeInTheDocument();
    expect(screen.getByText("new@example.com")).toBeInTheDocument();
  });

  it("says so when the email is taken", async () => {
    fake.signUp.mockRejectedValue(new ApiError(409, "An account with this email already exists."));
    renderApp("/signup");
    await screen.findByRole("heading", { name: "Create your account" });
    await fillAndSubmit("taken@example.com", "long enough", /create account/i);
    expect(await screen.findByRole("alert")).toHaveTextContent("already exists");
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  });

  it("lets the password be revealed", async () => {
    renderApp("/signup");
    await screen.findByRole("heading", { name: "Create your account" });
    const password = screen.getByLabelText("Password");
    expect(password).toHaveAttribute("type", "password");
    await userEvent.setup().click(screen.getByRole("button", { name: "Show" }));
    expect(password).toHaveAttribute("type", "text");
  });
});

describe("sign out and switching users", () => {
  it("signs out, forgets cached data and returns to sign-in", async () => {
    fake.user = ALICE;
    const { router, queryClient } = renderApp("/history");
    await screen.findByRole("heading", { name: "History page" });
    queryClient.setQueryData(["analyses"], { pages: [{ items: [{ id: "alices-serve" }] }] });
    await userEvent.setup().click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(fake.logOut).toHaveBeenCalled();
    expect(where(router)).toBe("/login");
    expect(queryClient.getQueryData(["analyses"])).toBeUndefined();
    expect(screen.queryByText("alice@example.com")).not.toBeInTheDocument();
  });

  it("still signs out locally if the server can't be reached", async () => {
    fake.user = ALICE;
    fake.logOut.mockRejectedValue(new TypeError("Failed to fetch"));
    renderApp("/");
    await screen.findByRole("heading", { name: "Upload page" });
    await userEvent.setup().click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("drops the previous user's cached data when someone else signs in", async () => {
    const { queryClient } = renderApp("/login");
    await screen.findByRole("heading", { name: "Sign in" });
    queryClient.setQueryData(["analyses"], { pages: [{ items: [{ id: "someone-elses" }] }] });
    await fillAndSubmit("bob@example.com", "correct horse", /sign in/i);
    await screen.findByRole("heading", { name: "Upload page" });
    expect(queryClient.getQueryData(["analyses"])).toBeUndefined();
    expect(queryClient.getQueryData(sessionKey)).toMatchObject({ email: "bob@example.com" });
  });
});

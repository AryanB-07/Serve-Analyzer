import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, Outlet } from "react-router";
import { RouterProvider } from "react-router/dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Notification } from "../api/types";

const fake = vi.hoisted(() => ({
  items: [] as Notification[],
  listNotifications: vi.fn(),
  countNotifications: vi.fn(),
  markNotificationsRead: vi.fn(),
}));
vi.mock("../api", async () => {
  const client = await import("../api/client");
  return { api: fake, USE_MOCKS: false, ApiError: client.ApiError, UploadAbortedError: client.UploadAbortedError };
});

const { createQueryClient } = await import("../api/session");
const { NotificationBell } = await import("./NotificationBell");

const person = (username: string, display_name: string | null = null) => ({ username, display_name, avatar_url: null });

beforeEach(() => {
  fake.items = [
    { id: "n1", kind: "serve_received", person: person("ann", "Ann A"), conversation_id: "c1", created_at: new Date().toISOString(), read: false },
    { id: "n2", kind: "request_accepted", person: person("bob"), conversation_id: null, created_at: "2026-10-01T10:00:00Z", read: false },
    { id: "n3", kind: "request_received", person: person("carol"), conversation_id: null, created_at: "2026-09-01T10:00:00Z", read: true },
  ];
  fake.listNotifications.mockReset().mockImplementation(async () => fake.items);
  fake.countNotifications.mockReset().mockImplementation(async () => fake.items.filter((n) => !n.read).length);
  fake.markNotificationsRead.mockReset().mockImplementation(async () => {
    fake.items = fake.items.map((n) => ({ ...n, read: true }));
  });
});

function renderBell() {
  const router = createMemoryRouter(
    [{ element: <><NotificationBell /><Outlet /></>, children: [{ path: "*", element: <h1>Page</h1> }] }],
    { initialEntries: ["/"] },
  );
  render(<QueryClientProvider client={createQueryClient()}><RouterProvider router={router} /></QueryClientProvider>);
  return router;
}

describe("the notification bell", () => {
  it("counts what's new, and marks it read when opened", async () => {
    renderBell();
    const bell = await screen.findByRole("button", { name: "Notifications, 2 new" });
    await userEvent.click(bell);
    const ann = await screen.findByRole("link", { name: /Ann A sent you a serve/ });
    expect(ann).toHaveAttribute("href", "/messages/c1");
    expect(screen.getByRole("link", { name: /@bob accepted your friend request/ })).toHaveAttribute("href", "/u/bob");
    expect(screen.getByRole("link", { name: /@carol sent you a friend request/ })).toHaveAttribute("href", "/friends");
    expect(within(ann).getByText("(new)")).toBeInTheDocument();
    await vi.waitFor(() => expect(fake.markNotificationsRead).toHaveBeenCalled());
    expect(await screen.findByRole("button", { name: "Notifications" })).toBeInTheDocument();
  });

  it("closes on Escape and on following one", async () => {
    const router = renderBell();
    const bell = await screen.findByRole("button", { name: /Notifications/ });
    await userEvent.click(bell);
    await userEvent.keyboard("{Escape}");
    expect(bell).toHaveAttribute("aria-expanded", "false");
    expect(bell).toHaveFocus();
    await userEvent.click(bell);
    await userEvent.click(await screen.findByRole("link", { name: /accepted your friend request/ }));
    expect(router.state.location.pathname).toBe("/u/bob");
    expect(bell).toHaveAttribute("aria-expanded", "false");
  });

  it("says when there's nothing", async () => {
    fake.items = [];
    renderBell();
    await userEvent.click(await screen.findByRole("button", { name: "Notifications" }));
    expect(await screen.findByText(/Nothing new/)).toBeInTheDocument();
    expect(fake.markNotificationsRead).not.toHaveBeenCalled();
  });
});

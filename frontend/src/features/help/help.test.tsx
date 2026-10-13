/** The help dialog: the ? button, its topics, keyboard use, and links that open a topic. */
import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
// The app's RouterProvider (main.tsx): only this one honours navigate()'s flushSync.
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const fake = vi.hoisted(() => ({ getMe: vi.fn() }));

vi.mock("../../api", async () => {
  const client = await import("../../api/client");
  return { api: fake, USE_MOCKS: false, ApiError: client.ApiError, UploadAbortedError: client.UploadAbortedError };
});

const { createQueryClient } = await import("../../api/session");
const { AppShell } = await import("../../components/AppShell");
const { HelpProvider, HELP_PARAM, useHelp } = await import("./HelpProvider");
const { HELP_TOPICS } = await import("./topics");

beforeEach(() => {
  fake.getMe.mockReset().mockResolvedValue(null);
});

function renderApp(path = "/", page = <h1>Some page</h1>) {
  const router = createMemoryRouter(
    [{ element: <AppShell />, children: [{ path: "*", element: page }] }],
    { initialEntries: [path] },
  );
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

const helpParam = (router: ReturnType<typeof renderApp>) =>
  new URLSearchParams(router.state.location.search).get(HELP_PARAM);

describe("the help button", () => {
  it("opens a dialog listing every topic, at the first one", async () => {
    const router = renderApp();
    const button = await screen.findByRole("button", { name: "Help" });
    expect(button).toHaveAttribute("aria-haspopup", "dialog");
    await userEvent.click(button);
    const dialog = screen.getByRole("dialog", { name: "Help" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    const tabs = within(dialog).getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(HELP_TOPICS.map((t) => t.title));
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(tabs[0]).toHaveFocus();
    expect(within(dialog).getByRole("tabpanel")).toHaveTextContent("Film one serve, side-on");
    expect(helpParam(router)).toBe("getting-started");
  });

  it("shows the filming guide again, diagram and all", async () => {
    renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "Help" }));
    await userEvent.click(screen.getByRole("tab", { name: "How to film your serve" }));
    const panel = screen.getByRole("tabpanel", { name: "How to film your serve" });
    expect(within(panel).getByRole("img", { name: /Camera placement, seen from above/ })).toBeInTheDocument();
    expect(panel).toHaveTextContent("5–10 m away, at hip height");
    expect(panel).toHaveTextContent("30 fps or more, good light");
  });

  it("has the known limits and the keyboard shortcuts too", async () => {
    renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "Help" }));
    await userEvent.click(screen.getByRole("tab", { name: "What the analysis can't do" }));
    expect(screen.getByRole("tabpanel")).toHaveTextContent("A swing that misses the ball looks just like a serve");
    await userEvent.click(screen.getByRole("tab", { name: "Keyboard shortcuts" }));
    expect(within(screen.getByRole("tabpanel")).getByRole("table")).toHaveTextContent("Play or pause");
  });

  it("closes with Escape and gives focus back to the button", async () => {
    const router = renderApp();
    const button = await screen.findByRole("button", { name: "Help" });
    await userEvent.click(button);
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(button).toHaveFocus();
    expect(helpParam(router)).toBeNull();
  });

  it("closes from its close button and from the backdrop", async () => {
    renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "Help" }));
    await userEvent.click(screen.getByRole("button", { name: "Close help" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Help" }));
    await userEvent.click(screen.getByRole("dialog").parentElement!);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("doesn't close when clicking inside it", async () => {
    renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "Help" }));
    await userEvent.click(screen.getByRole("tabpanel"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("closes with the browser's back button", async () => {
    const router = renderApp("/history");
    await userEvent.click(await screen.findByRole("button", { name: "Help" }));
    await userEvent.click(screen.getByRole("tab", { name: "Keyboard shortcuts" }));
    await act(() => router.navigate(-1));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/history");
  });

  it("makes the page behind inert and keeps it from scrolling", async () => {
    renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "Help" }));
    expect(screen.getByRole("heading", { name: "Some page", hidden: true }).closest("[inert]")).not.toBeNull();
    expect(document.documentElement.style.overflow).toBe("hidden");
    await userEvent.keyboard("{Escape}");
    expect(screen.getByRole("heading", { name: "Some page" }).closest("[inert]")).toBeNull();
    expect(document.documentElement.style.overflow).toBe("");
  });
});

describe("keyboard use", () => {
  it("moves between topics with the arrow keys, Home and End", async () => {
    renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "Help" }));
    const tab = (name: string) => screen.getByRole("tab", { name });
    await userEvent.keyboard("{ArrowDown}");
    expect(tab("How to film your serve")).toHaveFocus();
    expect(tab("How to film your serve")).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("{ArrowRight}");
    expect(tab("What the analysis can't do")).toHaveFocus();
    await userEvent.keyboard("{End}");
    expect(tab("Keyboard shortcuts")).toHaveFocus();
    await userEvent.keyboard("{ArrowDown}");
    expect(tab("Getting started")).toHaveFocus(); // wraps round
    await userEvent.keyboard("{ArrowUp}");
    expect(tab("Keyboard shortcuts")).toHaveFocus();
    await userEvent.keyboard("{Home}");
    expect(tab("Getting started")).toHaveFocus();
    // Only the selected tab is in the tab order.
    expect(screen.getAllByRole("tab").filter((t) => t.tabIndex === 0)).toHaveLength(1);
  });

  it("keeps Tab inside the dialog", async () => {
    renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "Help" }));
    const dialog = screen.getByRole("dialog");
    for (let i = 0; i < 6; i++) {
      await userEvent.tab();
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
    for (let i = 0; i < 6; i++) {
      await userEvent.tab({ shift: true });
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
  });
});

describe("opening a topic from a link or from code", () => {
  it("opens at the topic in ?help=", async () => {
    renderApp("/history?help=filming");
    expect(await screen.findByRole("tab", { name: "How to film your serve" })).toHaveAttribute("aria-selected", "true");
  });

  it("opens an unknown topic's link at the first topic", async () => {
    renderApp("/?help=no-such-topic");
    expect(await screen.findByRole("tab", { name: "Getting started" })).toHaveAttribute("aria-selected", "true");
  });

  it("keeps the rest of the address when opening and closing", async () => {
    const router = renderApp("/analyses/a1?tab=charts");
    await userEvent.click(await screen.findByRole("button", { name: "Help" }));
    await userEvent.keyboard("{Escape}");
    expect(router.state.location.pathname).toBe("/analyses/a1");
    expect(router.state.location.search).toBe("?tab=charts");
  });

  it("lets any page open help at a topic", async () => {
    function NeedHelp() {
      const { openHelp } = useHelp();
      return <button type="button" onClick={() => openHelp("limits")}>What are the limits?</button>;
    }
    renderApp("/", <NeedHelp />);
    await userEvent.click(await screen.findByRole("button", { name: "What are the limits?" }));
    expect(screen.getByRole("tab", { name: "What the analysis can't do" })).toHaveAttribute("aria-selected", "true");
  });

  it("takes new topics without changes to the dialog", async () => {
    const extra = [...HELP_TOPICS, { id: "new-feature", title: "A new feature", Body: () => <p>How the new feature works.</p> }];
    const router = createMemoryRouter(
      [{ path: "*", element: <HelpProvider topics={extra}><p>page</p></HelpProvider> }],
      { initialEntries: ["/?help=new-feature"] },
    );
    render(<RouterProvider router={router} />);
    expect(await screen.findByRole("tab", { name: "A new feature" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("How the new feature works.");
  });

  it("needs a provider", () => {
    function Orphan() {
      useHelp();
      return null;
    }
    vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Orphan />)).toThrow(/HelpProvider/);
  });
});

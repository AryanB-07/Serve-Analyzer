/** The feed: Public and Friends tabs, loading, empty and error states, more as you scroll, one video at a time. */
import { QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { FeedTab, Post, PostPage } from "../../api/types";

const post = (id: string, name: string, visibility: Post["visibility"] = "public"): Post => ({
  id, author: { username: name.toLowerCase(), display_name: name, avatar_url: null }, is_yours: false, caption: `${name}'s serve`,
  visibility, hand: "right", overall_score: 70, key_scores: null, recorded_at: "2026-10-11T10:00:00Z", created_at: "2026-10-11T10:05:00Z",
  video_url: `/v/${id}.mp4`, thumbnail_url: `/t/${id}.jpg`, like_count: 0, comment_count: 0, liked_by_you: false,
});

const fake = vi.hoisted(() => ({
  pages: {} as Record<string, (PostPage | Error)[]>,
  getFeed: vi.fn(),
  like: vi.fn(),
  unlike: vi.fn(),
}));
vi.mock("../../api", async () => {
  const client = await import("../../api/client");
  return { api: fake, USE_MOCKS: false, ApiError: client.ApiError, UploadAbortedError: client.UploadAbortedError };
});

const { ApiError } = await import("../../api/client");
const { createQueryClient } = await import("../../api/session");
const { FeedPage } = await import("./FeedPage");

// jsdom has no IntersectionObserver; this one lets a test say when the end of the list comes into view.
let observed: ((entries: { isIntersecting: boolean }[]) => void)[] = [];
class FakeObserver {
  constructor(private callback: (entries: { isIntersecting: boolean }[]) => void) {}
  observe() { observed.push(this.callback); }
  disconnect() { observed = observed.filter((c) => c !== this.callback); }
}
const scrollToEnd = () => act(() => observed.forEach((c) => c([{ isIntersecting: true }])));

beforeEach(() => {
  observed = [];
  vi.stubGlobal("IntersectionObserver", FakeObserver);
  fake.pages = {
    public: [{ items: [post("a", "Ann"), post("b", "Bob")], next_cursor: "c1" }, { items: [post("c", "Cal")], next_cursor: null }],
    friends: [{ items: [post("f", "Fay", "friends")], next_cursor: null }],
  };
  fake.getFeed.mockReset().mockImplementation(async (tab: FeedTab, cursor?: string) => {
    const page = fake.pages[tab]![cursor ? 1 : 0]!;
    if (page instanceof Error) throw page;
    return page;
  });
});
afterEach(() => vi.unstubAllGlobals());

function renderAt(path = "/feed") {
  const router = createMemoryRouter([{ path: "/feed", element: <FeedPage /> }], { initialEntries: [path] });
  render(<QueryClientProvider client={createQueryClient()}><RouterProvider router={router} /></QueryClientProvider>);
  return router;
}

const names = () => screen.queryAllByRole("article").map((a) => a.getAttribute("aria-label"));

describe("the feed", () => {
  it("shows placeholders while loading, then public posts, and more when you scroll to the end", async () => {
    renderAt();
    expect(screen.getByRole("status")).toHaveTextContent("Loading posts…");
    expect(await screen.findByRole("article", { name: "Ann's post" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Public" })).toHaveAttribute("aria-selected", "true");
    expect(names()).toEqual(["Ann's post", "Bob's post"]);
    expect(fake.getFeed).toHaveBeenCalledWith("public", undefined);

    scrollToEnd();
    expect(await screen.findByRole("article", { name: "Cal's post" })).toBeInTheDocument();
    expect(fake.getFeed).toHaveBeenLastCalledWith("public", "c1");
    expect(screen.getByText("You're all caught up.")).toBeInTheDocument();
    expect(fake.getFeed).toHaveBeenCalledTimes(2);
  });

  it("loads more with the button too", async () => {
    renderAt();
    await userEvent.click(await screen.findByRole("button", { name: "Load more" }));
    expect(await screen.findByRole("article", { name: "Cal's post" })).toBeInTheDocument();
  });

  it("switches to friends' posts, and remembers the tab in the address", async () => {
    const router = renderAt();
    await screen.findByRole("article", { name: "Ann's post" });
    await userEvent.click(screen.getByRole("tab", { name: "Friends" }));
    expect(await screen.findByRole("article", { name: "Fay's post" })).toBeInTheDocument();
    expect(names()).toEqual(["Fay's post"]);
    expect(router.state.location.search).toBe("?tab=friends");
    expect(screen.getByRole("tabpanel")).toHaveAccessibleName("Friends");
  });

  it("says what to do when a tab is empty", async () => {
    fake.pages.friends = [{ items: [], next_cursor: null }];
    fake.pages.public = [{ items: [], next_cursor: null }];
    renderAt("/feed?tab=friends");
    expect(await screen.findByText("No posts from friends yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Find people to follow" })).toHaveAttribute("href", "/friends");
    await userEvent.click(screen.getByRole("tab", { name: "Public" }));
    expect(await screen.findByText("No public posts yet")).toBeInTheDocument();
  });

  it("says when it can't load, and tries again", async () => {
    fake.pages.public = [new ApiError(429, "Too many requests. Try again in a minute.")];
    renderAt();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("We couldn't load the feed");
    fake.pages.public = [{ items: [post("a", "Ann")], next_cursor: null }];
    await userEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("article", { name: "Ann's post" })).toBeInTheDocument();
  });

  it("keeps what it has when the next page fails, and stops asking until you try again", async () => {
    fake.pages.public![1] = new ApiError(429, "Too many requests.");
    renderAt();
    await screen.findByRole("article", { name: "Ann's post" });
    scrollToEnd();
    expect(await screen.findByText("We couldn't load more posts.")).toBeInTheDocument();
    expect(names()).toEqual(["Ann's post", "Bob's post"]);
    scrollToEnd();
    expect(fake.getFeed).toHaveBeenCalledTimes(2);
    fake.pages.public![1] = { items: [post("c", "Cal")], next_cursor: null };
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("article", { name: "Cal's post" })).toBeInTheDocument();
  });

  it("doesn't load videos until played, and plays one at a time", async () => {
    renderAt();
    await screen.findByRole("article", { name: "Bob's post" });
    const ann = screen.getByLabelText("Ann's serve") as HTMLVideoElement;
    const bob = screen.getByLabelText("Bob's serve");
    expect(ann).toHaveAttribute("preload", "none");
    expect(ann).not.toHaveAttribute("autoplay");
    const pause = vi.fn();
    Object.defineProperty(ann, "paused", { value: false });
    ann.pause = pause;
    fireEvent.play(bob);
    expect(pause).toHaveBeenCalledTimes(1);
  });
});

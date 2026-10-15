/** Posts: the card, likes, a post's page with comments, editing and deleting, and posting a serve. */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Comment, Post } from "../../api/types";

const BOB = { username: "bob", display_name: "Bob B", avatar_url: null };
const ME = { username: "alice", display_name: "Alice", avatar_url: null };
const POST: Post = {
  id: "p1", author: BOB, is_yours: false, caption: "Trophy position finally clicking.", visibility: "friends", hand: "right",
  overall_score: 83, key_scores: null, recorded_at: "2026-10-11T10:00:00Z", created_at: "2026-10-11T10:05:00Z",
  video_url: "/api/storage/posts/p1/video.mp4?sig=x", thumbnail_url: "/api/storage/posts/p1/thumbnail.jpg?sig=x",
  like_count: 2, comment_count: 2, liked_by_you: false,
};
const comment = (id: string, author: typeof BOB, body: string, can_delete: boolean): Comment =>
  ({ id, author, body, created_at: "2026-10-11T11:00:00Z", can_delete });

const fake = vi.hoisted(() => ({
  post: null as unknown as Post | Error,
  comments: [] as Comment[],
  getPost: vi.fn(),
  like: vi.fn(),
  unlike: vi.fn(),
  listComments: vi.fn(),
  addComment: vi.fn(),
  deleteComment: vi.fn(),
  editPost: vi.fn(),
  deletePost: vi.fn(),
  createPost: vi.fn(),
  report: vi.fn(),
  block: vi.fn(),
}));
vi.mock("../../api", async () => {
  const client = await import("../../api/client");
  return { api: fake, USE_MOCKS: false, ApiError: client.ApiError, UploadAbortedError: client.UploadAbortedError };
});

const { ApiError } = await import("../../api/client");
const { createQueryClient } = await import("../../api/session");
const { PostPage } = await import("./PostPage");
const { CreatePost } = await import("./CreatePost");

beforeEach(() => {
  fake.post = POST;
  fake.comments = [comment("c1", BOB, "First!", false), comment("c2", ME, "Nice serve", true)];
  fake.getPost.mockReset().mockImplementation(async () => {
    if (fake.post instanceof Error) throw fake.post;
    return fake.post;
  });
  fake.like.mockReset().mockImplementation(async () => ({ liked: true, like_count: (fake.post as Post).like_count + 1 }));
  fake.unlike.mockReset().mockImplementation(async () => ({ liked: false, like_count: (fake.post as Post).like_count - 1 }));
  fake.listComments.mockReset().mockImplementation(async () => ({ items: fake.comments, next_cursor: null }));
  fake.addComment.mockReset().mockImplementation(async (_id: string, body: string) => {
    const c = comment(`c${fake.comments.length + 1}`, ME, body, true);
    fake.comments = [...fake.comments, c];
    return c;
  });
  fake.deleteComment.mockReset().mockImplementation(async (id: string) => {
    fake.comments = fake.comments.filter((c) => c.id !== id);
  });
  fake.editPost.mockReset().mockImplementation(async (_id: string, body: Partial<Post>) => (fake.post = { ...(fake.post as Post), ...body }));
  fake.deletePost.mockReset().mockResolvedValue(undefined);
  fake.createPost.mockReset().mockResolvedValue({ ...POST, id: "new1", is_yours: true, author: ME });
  fake.report.mockReset().mockResolvedValue(undefined);
});

function renderAt(path: string, element = <PostPage />) {
  const router = createMemoryRouter(
    [
      { path: "/p/:id", element },
      { path: "/analyses/:id", element },
      { path: "/profile", element: <h1>Profile page</h1> },
    ],
    { initialEntries: [path] },
  );
  render(<QueryClientProvider client={createQueryClient()}><RouterProvider router={router} /></QueryClientProvider>);
  return router;
}

describe("a post", () => {
  it("shows who posted it, for whom, the caption and score, and doesn't load the video until played", async () => {
    renderAt("/p/p1");
    const card = await screen.findByRole("article", { name: "Bob B's post" });
    expect(within(card).getByRole("link", { name: "Bob B" })).toHaveAttribute("href", "/u/bob");
    expect(within(card).getByText("Friends")).toBeInTheDocument();
    expect(within(card).getByText("Trophy position finally clicking.")).toBeInTheDocument();
    expect(within(card).getByText("83").className).toMatch(/text-good/);
    const video = within(card).getByLabelText("Bob B's serve");
    expect(video).toHaveAttribute("preload", "none");
    expect(video).toHaveAttribute("poster", POST.thumbnail_url);
  });

  it("likes and unlikes at once, and puts it back if the server refuses", async () => {
    renderAt("/p/p1");
    const like = await screen.findByRole("button", { name: /^Like Bob B's post, 2 likes/ });
    expect(like).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(like);
    expect(await screen.findByRole("button", { name: /^Unlike Bob B's post, 3 likes/ })).toHaveAttribute("aria-pressed", "true");
    expect(fake.like).toHaveBeenCalledWith("p1");

    fake.unlike.mockRejectedValueOnce(new ApiError(404, "Post not found"));
    await userEvent.click(screen.getByRole("button", { name: /^Unlike/ }));
    expect(await screen.findByRole("button", { name: /^Unlike Bob B's post, 3 likes/ })).toBeInTheDocument();
  });

  it("says when a post can't be seen", async () => {
    fake.post = new ApiError(404, "Post not found");
    renderAt("/p/nope");
    expect(await screen.findByRole("heading", { name: "Post not found" })).toBeInTheDocument();
    expect(fake.getPost).toHaveBeenCalledTimes(1);
  });
});

describe("comments", () => {
  it("are in order, and a new one is added with Enter", async () => {
    renderAt("/p/p1");
    const list = await screen.findByRole("region", { name: "Comments" });
    expect((await within(list).findAllByRole("listitem")).map((li) => li.textContent)).toEqual([
      expect.stringContaining("First!"), expect.stringContaining("Nice serve")]);
    await userEvent.type(screen.getByLabelText("Comment"), "Great toss{Enter}");
    expect(fake.addComment).toHaveBeenCalledWith("p1", "Great toss");
    expect(await within(list).findByText("Great toss")).toBeInTheDocument();
    expect(screen.getByLabelText("Comment")).toHaveValue("");
  });

  it("can be deleted when they're yours, after confirming; others' can be reported", async () => {
    renderAt("/p/p1");
    await screen.findByText("Nice serve");
    expect(screen.queryByRole("button", { name: "Delete Bob B's comment" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Delete Alice's comment" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, delete it" }));
    expect(fake.deleteComment).toHaveBeenCalledWith("c2");
    await userEvent.click(screen.getByRole("button", { name: "Report Bob B's comment" }));
    const form = screen.getByRole("form", { name: "Report Bob B's comment" });
    await userEvent.click(within(form).getByLabelText("Spam"));
    await userEvent.click(within(form).getByRole("button", { name: "Send report" }));
    expect(fake.report).toHaveBeenCalledWith(expect.objectContaining({ username: "bob", comment_id: "c1", reason: "spam" }));
  });

  it("on your post, you can delete anyone's", async () => {
    fake.post = { ...POST, is_yours: true, author: ME };
    fake.comments = [comment("c1", BOB, "First!", true)];
    renderAt("/p/p1");
    expect(await screen.findByRole("button", { name: "Delete Bob B's comment" })).toBeInTheDocument();
  });
});

describe("your own post", () => {
  beforeEach(() => {
    fake.post = { ...POST, is_yours: true, author: ME };
  });

  it("can be edited: caption and who can see it", async () => {
    renderAt("/p/p1");
    await userEvent.click(await screen.findByRole("button", { name: "Edit post" }));
    const form = screen.getByRole("form", { name: "Edit post" });
    await userEvent.clear(within(form).getByLabelText("Caption"));
    await userEvent.type(within(form).getByLabelText("Caption"), "New caption");
    await userEvent.click(within(form).getByLabelText(/^Public/));
    await userEvent.click(within(form).getByRole("button", { name: "Save" }));
    expect(fake.editPost).toHaveBeenCalledWith("p1", { caption: "New caption", visibility: "public" });
    expect(await screen.findByText("New caption")).toBeInTheDocument();
  });

  it("is deleted after confirming, and you go back to your profile", async () => {
    const router = renderAt("/p/p1");
    await userEvent.click(await screen.findByRole("button", { name: "Delete…" }));
    expect(screen.getByText(/Your serve stays in My Serves/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Delete post" }));
    expect(fake.deletePost).toHaveBeenCalledWith("p1");
    await vi.waitFor(() => expect(router.state.location.pathname).toBe("/profile"));
  });

  it("has no Report button", async () => {
    renderAt("/p/p1");
    await screen.findByRole("button", { name: "Edit post" });
    expect(screen.queryByRole("button", { name: /Report this post/ })).not.toBeInTheDocument();
  });
});

describe("posting a serve", () => {
  const summary = { id: "a1", hand: "right", status: "succeeded", filename: "s.mp4", created_at: "2026-10-10T10:00:00Z",
    updated_at: "2026-10-10T10:00:00Z", error: null, thumbnail_url: null } as const;

  it("defaults to friends, takes a caption, and links to the post", async () => {
    renderAt("/analyses/a1", <CreatePost summary={summary} />);
    await userEvent.click(await screen.findByRole("button", { name: "Post this serve" }));
    const form = screen.getByRole("form", { name: "Post this serve" });
    expect(within(form).getByLabelText(/^Friends/)).toBeChecked();
    expect(within(form).getByText(/never your note or the file's name/)).toBeInTheDocument();
    await userEvent.type(within(form).getByLabelText(/Caption/), "Working on the toss");
    await userEvent.click(within(form).getByRole("button", { name: "Post" }));
    expect(fake.createPost).toHaveBeenCalledWith({ analysis_id: "a1", caption: "Working on the toss", visibility: "friends" });
    expect(await screen.findByRole("link", { name: "View your post" })).toHaveAttribute("href", "/p/new1");
  });

  it("can be public", async () => {
    renderAt("/analyses/a1", <CreatePost summary={summary} />);
    await userEvent.click(await screen.findByRole("button", { name: "Post this serve" }));
    const form = screen.getByRole("form", { name: "Post this serve" });
    await userEvent.click(within(form).getByLabelText(/^Public/));
    await userEvent.click(within(form).getByRole("button", { name: "Post" }));
    expect(fake.createPost).toHaveBeenCalledWith({ analysis_id: "a1", caption: null, visibility: "public" });
  });
});

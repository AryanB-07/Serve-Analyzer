/** Posting a real analysed serve: friends-only then public, likes, comments, moderation, deletion. */
import type { Browser, Page } from "@playwright/test";

import { expect, test } from "./fixtures";

import { deleteAccount, expectAccessible, newEmail, signUpAndVerify } from "./helpers";

const SAMPLE = new URL("../../tests/fixtures/sample_serve.mp4", import.meta.url).pathname;

async function personNamed(browser: Browser, baseURL: string | undefined, username: string, name: string): Promise<Page> {
  const page = await (await browser.newContext({ baseURL, ignoreHTTPSErrors: true })).newPage();
  await signUpAndVerify(page, newEmail(username), username);
  expect((await page.request.patch("/api/profile", { data: { display_name: name } })).status()).toBe(200);
  return page;
}

test("a post is for friends until it's public; likes, comments and deleting it", async ({ browser, baseURL }) => {
  const tag = Date.now().toString(36).slice(-6);
  const [annName, bobName, carolName] = [`ann_p${tag}`, `bob_p${tag}`, `carol_p${tag}`];
  const ann = await personNamed(browser, baseURL, annName, "Ann Post");
  const bob = await personNamed(browser, baseURL, bobName, "Bob Post");
  const carol = await personNamed(browser, baseURL, carolName, "Carol Post");

  // Ann analyses the sample serve and posts it: for friends, by default.
  await ann.goto("/");
  await ann.getByText("Right-handed", { exact: true }).click();
  await ann.getByTestId("file-input").setInputFiles(SAMPLE);
  await ann.getByRole("button", { name: "Analyze serve" }).click();
  await expect(ann.getByRole("heading", { name: "Coaching feedback" })).toBeVisible({ timeout: 4 * 60_000 });
  await ann.getByRole("button", { name: "Post this serve" }).click();
  const form = ann.getByRole("form", { name: "Post this serve" });
  await expect(form.getByLabel(/^Friends/)).toBeChecked();
  await form.getByLabel(/Caption/).fill("First serve I'm proud of");
  await form.getByRole("button", { name: "Post", exact: true }).click();
  await ann.getByRole("link", { name: "View your post" }).click();
  const postUrl = new URL(ann.url()).pathname;
  const postId = postUrl.split("/").pop();
  const card = ann.getByRole("article", { name: "Ann Post's post" });
  await expect(card.getByText("First serve I'm proud of")).toBeVisible();
  const video = card.getByLabel("Ann Post's serve");
  await expect(video).toHaveAttribute("preload", "none");
  const videoUrl = await video.getAttribute("src");
  expect((await ann.request.get(videoUrl!)).status()).toBe(200);

  // Bob isn't her friend yet: the post, its likes and comments, and its video are all closed to him.
  expect((await bob.request.get(`/api/posts/${postId}`)).status()).toBe(404);
  expect((await bob.request.put(`/api/posts/${postId}/like`)).status()).toBe(404);
  await bob.goto(postUrl);
  await expect(bob.getByRole("heading", { name: "Post not found" })).toBeVisible();

  // Friends now: Bob likes and comments.
  expect((await ann.request.put(`/api/follows/${bobName}`)).status()).toBe(200);
  expect((await bob.request.put(`/api/follows/${annName}`)).status()).toBe(200);
  await bob.reload();
  await bob.getByRole("button", { name: /^Like Ann Post's post, 0 likes/ }).click();
  await expect(bob.getByRole("button", { name: /^Unlike Ann Post's post, 1 like/ })).toBeVisible();
  await bob.getByLabel("Comment", { exact: true }).fill("Huge improvement!");
  await bob.getByLabel("Comment", { exact: true }).press("Enter");
  await expect(bob.getByRole("region", { name: "Comments" })).toContainText("Huge improvement!");
  await expectAccessible(bob, "a friend's post with comments");

  // Ann moderates her post: she deletes Bob's comment.
  await ann.reload();
  await ann.getByRole("button", { name: "Delete Bob Post's comment" }).click();
  await ann.getByRole("button", { name: "Yes, delete it" }).click();
  await expect(ann.getByRole("region", { name: "Comments" })).toContainText("No comments yet.");

  // Carol, a stranger, can't see it until Ann makes it public.
  expect((await carol.request.get(`/api/posts/${postId}`)).status()).toBe(404);
  await ann.getByRole("button", { name: "Edit post" }).click();
  await ann.getByRole("form", { name: "Edit post" }).getByLabel(/^Public/).check();
  await ann.getByRole("button", { name: "Save" }).click();
  await expect(card.getByText("Public")).toBeVisible();
  await carol.goto(`/u/${annName}`);
  await expect(carol.getByRole("article", { name: "Ann Post's post" })).toBeVisible();

  // Ann deletes the post: gone for everyone, with its video; her serve stays in My Serves.
  await ann.getByRole("button", { name: "Delete…" }).click();
  await ann.getByRole("button", { name: "Delete post" }).click();
  await expect(ann).toHaveURL(/\/profile$/);
  expect((await carol.request.get(`/api/posts/${postId}`)).status()).toBe(404);
  expect((await ann.request.get(videoUrl!)).status()).toBe(404);
  const serves = await (await ann.request.get("/api/analyses")).json();
  expect(serves.items).toHaveLength(1);

  for (const page of [ann, bob, carol]) {
    await deleteAccount(page);
    await page.context().close();
  }
});

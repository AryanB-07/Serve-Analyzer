/** The feed: friends see friends' posts, everyone signed in sees public ones, and more load as you scroll. */
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

test("the feed's public and friends tabs, paged as you scroll", async ({ browser, baseURL }) => {
  const tag = Date.now().toString(36).slice(-6);
  const [annName, bobName, carolName] = [`ann_f${tag}`, `bob_f${tag}`, `carol_f${tag}`];
  const ann = await personNamed(browser, baseURL, annName, "Ann Feed");
  const bob = await personNamed(browser, baseURL, bobName, "Bob Feed");
  const carol = await personNamed(browser, baseURL, carolName, "Carol Feed");
  expect((await ann.request.put(`/api/follows/${bobName}`)).status()).toBe(200);
  expect((await bob.request.put(`/api/follows/${annName}`)).status()).toBe(200);
  expect((await carol.request.put(`/api/follows/${annName}`)).status()).toBe(200); // one way: not a friend

  // Ann analyses a serve and posts it eleven times for everyone, then once for friends.
  await ann.goto("/");
  await ann.getByText("Right-handed", { exact: true }).click();
  await ann.getByTestId("file-input").setInputFiles(SAMPLE);
  await ann.getByRole("button", { name: "Analyze serve" }).click();
  await expect(ann.getByRole("heading", { name: "Coaching feedback" })).toBeVisible({ timeout: 4 * 60_000 });
  const analysisId = new URL(ann.url()).pathname.split("/").pop();
  for (let n = 1; n <= 11; n++) {
    const res = await ann.request.post("/api/posts", { data: { analysis_id: analysisId, caption: `${tag} public ${n}`, visibility: "public" } });
    expect(res.status()).toBe(201);
  }
  expect((await ann.request.post("/api/posts", { data: { analysis_id: analysisId, caption: `${tag} for friends` } })).status()).toBe(201);

  // Bob, her friend: the public tab shows the newest first, and the oldest arrives as he scrolls down.
  await bob.goto("/feed");
  await expect(bob.getByRole("tab", { name: "Public" })).toHaveAttribute("aria-selected", "true");
  await expect(bob.getByText(`${tag} public 11`, { exact: true })).toBeVisible();
  await expect(bob.getByText(`${tag} for friends`, { exact: true })).toHaveCount(0);
  await expect(bob.getByText(`${tag} public 1`, { exact: true })).toHaveCount(0);
  await bob.getByLabel("Ann Feed's serve").first().scrollIntoViewIfNeeded();
  await bob.mouse.wheel(0, 20_000);
  await expect(bob.getByText(`${tag} public 1`, { exact: true })).toBeVisible();
  for (const video of await bob.getByLabel("Ann Feed's serve").all()) await expect(video).toHaveAttribute("preload", "none");
  await expectAccessible(bob, "the public feed");

  // His friends tab has her friends-only post too, and he can like it from there.
  await bob.getByRole("tab", { name: "Friends" }).click();
  await expect(bob).toHaveURL(/\?tab=friends$/);
  const friendsPost = bob.getByRole("article", { name: "Ann Feed's post" }).filter({ hasText: `${tag} for friends` });
  await expect(friendsPost).toBeVisible();
  await friendsPost.getByRole("button", { name: /^Like Ann Feed's post, 0 likes/ }).click();
  await expect(friendsPost.getByRole("button", { name: /^Unlike Ann Feed's post, 1 like/ })).toBeVisible();
  await bob.reload();
  await expect(friendsPost.getByRole("button", { name: /^Unlike Ann Feed's post, 1 like/ })).toBeVisible();
  await expectAccessible(bob, "the friends feed");

  // Carol only follows Ann: her friends tab is empty, and the public tab never has the friends-only post.
  await carol.goto("/feed?tab=friends");
  await expect(carol.getByText("No posts from friends yet")).toBeVisible();
  const carolPublic = await (await carol.request.get("/api/feed?tab=public&limit=30")).json();
  const captions = carolPublic.items.map((p: { caption: string }) => p.caption);
  expect(captions).toContain(`${tag} public 1`);
  expect(captions).not.toContain(`${tag} for friends`);

  // Ann's own posts are in Public but not in her Friends tab.
  const annFriends = await (await ann.request.get("/api/feed?tab=friends")).json();
  expect(annFriends.items).toHaveLength(0);

  for (const page of [ann, bob, carol]) {
    await deleteAccount(page);
    await page.context().close();
  }
});

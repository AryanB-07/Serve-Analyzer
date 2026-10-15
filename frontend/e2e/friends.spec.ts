/** Following through the real stack: a follow, a follow back (friends), sharing, then a block. */
import type { Browser, Page } from "@playwright/test";

import { expect, test } from "./fixtures";

import { deleteAccount, expectAccessible, newEmail, signUpAndVerify } from "./helpers";

async function personWithUsername(browser: Browser, baseURL: string | undefined, username: string, name: string): Promise<Page> {
  const page = await (await browser.newContext({ baseURL, ignoreHTTPSErrors: true })).newPage();
  await signUpAndVerify(page, newEmail(username));
  const res = await page.request.patch("/api/profile", { data: { username, display_name: name, bio: `${name}'s bio` } });
  expect(res.status()).toBe(200);
  return page;
}

test("a follow, a follow back that makes friends, and a block that hides each from the other", async ({ browser, baseURL }) => {
  const tag = Date.now().toString(36).slice(-6);
  const [annName, bobName] = [`ann_${tag}`, `bob_${tag}`];
  const ann = await personWithUsername(browser, baseURL, annName, "Ann E2E");
  const bob = await personWithUsername(browser, baseURL, bobName, "Bob E2E");

  // Ann finds Bob by his username and follows him. She doesn't see his bio: they aren't friends yet.
  await ann.goto("/friends");
  await ann.getByRole("form", { name: "Find someone" }).getByLabel(/username/).fill(bobName.toUpperCase());
  await ann.getByRole("button", { name: "Find" }).click();
  await expect(ann).toHaveURL(new RegExp(`/u/${bobName}$`));
  await expect(ann.getByRole("heading", { level: 1, name: "Bob E2E" })).toBeVisible();
  await expect(ann.getByText("Bob E2E's bio")).toHaveCount(0);
  await ann.getByRole("button", { name: "Follow", exact: true }).click();
  await expect(ann.getByText(/You'll be friends if they follow you back/)).toBeVisible();
  // A double tap changes nothing.
  expect((await ann.request.put(`/api/follows/${bobName}`)).status()).toBe(200);
  // Following one way isn't enough to see Bob's lists.
  await expect(ann.getByRole("region", { name: /friends, followers and following/ })).toHaveCount(0);
  expect((await ann.request.get(`/api/people/${bobName}/followers`)).status()).toBe(403);

  // Bob is notified, sees Ann among his followers, and follows back from there.
  await bob.goto("/");
  await bob.getByRole("button", { name: "Notifications, 1 new" }).click();
  await expect(bob.getByRole("link", { name: /Ann E2E started following you/ })).toBeVisible();
  await expectAccessible(bob, "the notifications panel");
  await bob.keyboard.press("Escape");
  await bob.getByRole("link", { name: /^Friends/ }).click();
  await bob.getByRole("tab", { name: /Followers 1/ }).click();
  await bob.getByRole("button", { name: "Follow Ann E2E back" }).click();
  await bob.getByRole("tab", { name: /Friends 1/ }).click();
  await expect(bob.getByRole("tabpanel")).toContainText("Ann E2E");
  await expectAccessible(bob, "friends, with a friend");

  // Ann is told, and now sees his bio and counts.
  await ann.reload();
  await expect(ann.getByRole("button", { name: "Notifications, 1 new" })).toBeVisible();
  await expect(ann.getByText("Bob E2E's bio")).toBeVisible();
  await expect(ann.getByText(/^Friends since/)).toBeVisible();
  await expect(ann.getByText("1 friend", { exact: true })).toBeVisible();
  // As a friend, she can see his lists: she's on them.
  const bobsLists = ann.getByRole("region", { name: "Bob E2E's friends, followers and following" });
  await expect(bobsLists.getByRole("link", { name: "Ann E2E" })).toBeVisible();
  expect((await ann.request.get(`/api/people/${bobName}/followers`)).status()).toBe(200);

  // Nothing about his serves until he chooses to share; then his stats and a leaderboard place.
  await expect(ann.getByText("Bob E2E isn't sharing serve stats with friends.")).toBeVisible();
  await bob.goto("/settings#sharing");
  await bob.getByRole("checkbox", { name: /My serve stats/ }).check();
  await bob.getByRole("checkbox", { name: /Put me on the leaderboard/ }).check();
  await expect(bob.getByRole("checkbox", { name: /Put me on the leaderboard/ })).toBeChecked();
  await ann.reload();
  await expect(ann.getByRole("region", { name: "Bob E2E's serves" })).toContainText("Serves analyzed");
  await ann.goto("/friends");
  await expect(ann.getByRole("region", { name: "Leaderboard" })).toContainText("5 more serves to be ranked");

  // Unfollowing ends the friendship (Bob still follows Ann); following again restores it.
  await ann.goto(`/u/${bobName}`);
  await ann.getByRole("button", { name: "Unfriend…" }).click();
  await ann.getByRole("button", { name: "Unfollow", exact: true }).click();
  await expect(ann.getByText("Bob E2E follows you. Follow back to be friends.")).toBeVisible();
  await ann.getByRole("button", { name: "Follow back" }).click();
  await expect(ann.getByRole("button", { name: "Message" })).toBeVisible();

  // Bob blocks Ann: neither follows the other any more, and to Ann he doesn't exist.
  await bob.goto(`/u/${annName}`);
  await bob.getByRole("button", { name: "Block Ann E2E…" }).click();
  await bob.getByRole("button", { name: "Block Ann E2E" }).click();
  await expect(bob.getByRole("heading", { name: "You've blocked Ann E2E" })).toBeVisible();
  await ann.reload();
  await expect(ann.getByRole("heading", { name: "No one has that username" })).toBeVisible();
  const counts = await (await ann.request.get("/api/follows")).json();
  expect(counts).toEqual({ followers: 0, following: 0, friends: 0 });

  // Bob can unblock from Settings; the follows don't come back.
  await bob.goto("/settings#blocked");
  await bob.getByRole("button", { name: "Unblock Ann E2E" }).click();
  await expect(bob.getByText("You haven't blocked anyone.")).toBeVisible();
  await ann.goto(`/u/${bobName}`);
  await expect(ann.getByRole("button", { name: "Follow", exact: true })).toBeVisible();

  for (const page of [ann, bob]) {
    await deleteAccount(page);
    await page.context().close();
  }
});

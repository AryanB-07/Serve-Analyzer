/** Two people becoming friends through the real stack, then one blocking the other. */
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

test("a friend request, accepted, then a block that hides each from the other", async ({ browser, baseURL }) => {
  const tag = Date.now().toString(36).slice(-6);
  const [annName, bobName] = [`ann_${tag}`, `bob_${tag}`];
  const ann = await personWithUsername(browser, baseURL, annName, "Ann E2E");
  const bob = await personWithUsername(browser, baseURL, bobName, "Bob E2E");

  // Ann finds Bob by his username and asks. She sees only his name until he accepts.
  await ann.goto("/friends");
  await ann.getByRole("form", { name: "Find someone" }).getByLabel(/username/).fill(bobName.toUpperCase());
  await ann.getByRole("button", { name: "Find" }).click();
  await expect(ann).toHaveURL(new RegExp(`/u/${bobName}$`));
  await expect(ann.getByRole("heading", { level: 1, name: "Bob E2E" })).toBeVisible();
  await expect(ann.getByText("Bob E2E's bio")).toHaveCount(0);
  await ann.getByRole("button", { name: "Add friend" }).click();
  await expect(ann.getByText("Request sent.")).toBeVisible();

  // Bob sees a badge and a notification, and accepts from the Friends page.
  await bob.goto("/");
  await expect(bob.getByRole("link", { name: "Friends, 1 new request" })).toBeVisible();
  await bob.getByRole("button", { name: "Notifications, 1 new" }).click();
  await expect(bob.getByRole("link", { name: /Ann E2E sent you a friend request/ })).toBeVisible();
  await expectAccessible(bob, "the notifications panel");
  await bob.keyboard.press("Escape");
  await bob.getByRole("link", { name: /^Friends/ }).click();
  await bob.getByRole("button", { name: "Accept Ann E2E's request" }).click();
  await expect(bob.getByRole("region", { name: /Your friends \(1\)/ })).toContainText("Ann E2E");
  await expect(bob.getByRole("link", { name: "Friends", exact: true })).toBeVisible();

  // Ann is told, and now sees his bio.
  await ann.reload();
  await expect(ann.getByRole("button", { name: "Notifications, 1 new" })).toBeVisible();
  await expect(ann.getByText("Bob E2E's bio")).toBeVisible();
  await expect(ann.getByText(/^Friends since/)).toBeVisible();

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
  await expect(ann.getByRole("link", { name: "Join from Settings" })).toBeVisible();
  await ann.goto(`/u/${bobName}`);
  await expect(ann.getByRole("region", { name: "Bob E2E's serves" })).toBeVisible();

  // Bob blocks Ann: the friendship ends, and to Ann he doesn't exist.
  await bob.goto(`/u/${annName}`);
  await bob.getByRole("button", { name: "Block Ann E2E…" }).click();
  await bob.getByRole("button", { name: "Block Ann E2E" }).click();
  await expect(bob.getByRole("heading", { name: "You've blocked Ann E2E" })).toBeVisible();
  await ann.reload();
  await expect(ann.getByRole("heading", { name: "No one has that username" })).toBeVisible();
  await ann.goto("/friends");
  await expect(ann.getByRole("region", { name: /Your friends \(0\)/ })).toBeVisible();

  // Bob can unblock from Settings.
  await bob.goto("/settings#blocked");
  await bob.getByRole("button", { name: "Unblock Ann E2E" }).click();
  await expect(bob.getByText("You haven't blocked anyone.")).toBeVisible();
  await ann.goto(`/u/${bobName}`);
  await expect(ann.getByRole("button", { name: "Add friend" })).toBeVisible();

  // The data download lists the friendship history Bob has left: nothing, and no blocks.
  const data = await (await bob.request.get("/api/auth/me/export")).json();
  expect(data.connections).toEqual([]);
  expect(data.blocks).toEqual([]);

  for (const page of [ann, bob]) {
    await deleteAccount(page);
    await page.context().close();
  }
});

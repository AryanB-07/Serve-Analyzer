/** Two friends messaging through the real stack: send, read, Seen, delete, report, and the friendship ending. */
import type { Browser, Page } from "@playwright/test";

import { expect, test } from "./fixtures";

import { deleteAccount, expectAccessible, newEmail, signUpAndVerify } from "./helpers";

async function personWithUsername(browser: Browser, baseURL: string | undefined, username: string, name: string): Promise<Page> {
  const page = await (await browser.newContext({ baseURL, ignoreHTTPSErrors: true })).newPage();
  await signUpAndVerify(page, newEmail(username));
  expect((await page.request.patch("/api/profile", { data: { username, display_name: name } })).status()).toBe(200);
  return page;
}

test("friends message each other, and it closes when the friendship ends", async ({ browser, baseURL }) => {
  const tag = Date.now().toString(36).slice(-6);
  const [annName, bobName] = [`ann_m${tag}`, `bob_m${tag}`];
  const ann = await personWithUsername(browser, baseURL, annName, "Ann Msg");
  const bob = await personWithUsername(browser, baseURL, bobName, "Bob Msg");
  // Friends first: each follows the other (through the API; the UI for this is in friends.spec).
  expect((await ann.request.put(`/api/follows/${bobName}`)).status()).toBe(200);
  expect((await bob.request.put(`/api/follows/${annName}`)).status()).toBe(200);

  // Ann opens the conversation from Bob's page and sends two lines.
  await ann.goto(`/u/${bobName}`);
  await ann.getByRole("button", { name: "Message" }).click();
  await expect(ann).toHaveURL(/\/messages\/[0-9a-f]{32}$/);
  const box = ann.getByLabel("Message", { exact: true });
  await box.fill("Fancy a hit on Saturday?");
  await box.press("Enter");
  await expect(ann.getByRole("region", { name: "Messages with Bob Msg" })).toContainText("Fancy a hit on Saturday?");
  await box.fill("Bring the camera, I want to film my serve.");
  await ann.getByRole("button", { name: "Send", exact: true }).click();
  await expect(box).toHaveValue("");

  // Bob sees the unread badge, opens it, and answers. Ann's message is then marked Seen.
  await bob.goto("/");
  await expect(bob.getByRole("link", { name: "Messages, 2 new messages" })).toBeVisible();
  await bob.getByRole("link", { name: /^Messages/ }).click();
  await bob.getByRole("link", { name: /Ann Msg/ }).click();
  const thread = bob.getByRole("region", { name: "Messages with Ann Msg" });
  await expect(thread).toContainText("Bring the camera");
  await expect(bob.getByRole("link", { name: "Messages", exact: true })).toBeVisible(); // read now
  await bob.getByLabel("Message", { exact: true }).fill("Yes! 10am?");
  await bob.getByLabel("Message", { exact: true }).press("Enter");
  await expectAccessible(bob, "a conversation");
  // Ann's thread picks it up by polling, without a reload.
  await expect(ann.getByRole("region", { name: "Messages with Bob Msg" })).toContainText("Yes! 10am?", { timeout: 20_000 });

  // Ann deletes her second message for everyone.
  const annThread = ann.getByRole("region", { name: "Messages with Bob Msg" });
  await annThread.getByRole("listitem").filter({ hasText: "Bring the camera" }).getByRole("button", { name: "Delete" }).click();
  await annThread.getByRole("button", { name: "Yes, delete it" }).click();
  await expect(annThread.getByText("Message deleted")).toBeVisible();
  await bob.reload();
  await expect(thread.getByText("Message deleted")).toBeVisible();
  await expect(thread).not.toContainText("Bring the camera");

  // Ann reports Bob's message (it's kept for review).
  await annThread.getByRole("listitem").filter({ hasText: "Yes! 10am?" }).getByRole("button", { name: "Report" }).click();
  await ann.getByLabel("Something else").check();
  await ann.getByRole("button", { name: "Send report" }).click();
  await expect(ann.getByText(/We'll look at it/)).toBeVisible();
  await bob.goto("/messages");
  await expectAccessible(bob, "the messages list");

  // Bob unfollows Ann, which ends the friendship: the conversation stays readable, but closed.
  expect((await bob.request.delete(`/api/follows/${annName}`)).status()).toBe(204);
  await ann.reload();
  await expect(ann.getByText(/You're no longer friends\. You can still read the conversation\./)).toBeVisible();
  await expect(annThread).toContainText("Yes! 10am?");

  // Ann's data download has the conversation and her report.
  const data = await (await ann.request.get("/api/auth/me/export")).json();
  expect(data.conversations[0].with_username).toBe(bobName);
  expect(data.conversations[0].messages.map((m: { body: string | null }) => m.body)).toEqual(
    ["Fancy a hit on Saturday?", null, "Yes! 10am?"]);
  expect(data.reports_made[0]).toMatchObject({ username: bobName, reason: "other", message: "Yes! 10am?" });

  for (const page of [ann, bob]) {
    await deleteAccount(page);
    await page.context().close();
  }
});

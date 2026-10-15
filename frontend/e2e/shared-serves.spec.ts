/** Sending a real analysed serve to a friend: they open it read-only, and lose it when the message goes. */
import type { Browser, Page } from "@playwright/test";

import { expect, test } from "./fixtures";

import { deleteAccount, expectAccessible, newEmail, signUpAndVerify } from "./helpers";

const SAMPLE = new URL("../../tests/fixtures/sample_serve.mp4", import.meta.url).pathname;

async function personWithUsername(browser: Browser, baseURL: string | undefined, username: string, name: string): Promise<Page> {
  const page = await (await browser.newContext({ baseURL, ignoreHTTPSErrors: true })).newPage();
  await signUpAndVerify(page, newEmail(username));
  expect((await page.request.patch("/api/profile", { data: { username, display_name: name } })).status()).toBe(200);
  return page;
}

test("a serve sent to a friend opens read-only, until the message is deleted", async ({ browser, baseURL }) => {
  const tag = Date.now().toString(36).slice(-6);
  const [annName, bobName] = [`ann_s${tag}`, `bob_s${tag}`];
  const ann = await personWithUsername(browser, baseURL, annName, "Ann Share");
  const bob = await personWithUsername(browser, baseURL, bobName, "Bob Share");
  expect((await ann.request.post("/api/connections", { data: { username: bobName } })).status()).toBe(201);
  const requestId = (await (await bob.request.get("/api/connections")).json()).incoming[0].id;
  expect((await bob.request.post(`/api/connections/${requestId}/accept`)).status()).toBe(200);

  // Ann analyses the sample serve, then sends it to Bob from its results page.
  await ann.goto("/");
  await ann.getByText("Right-handed", { exact: true }).click();
  await ann.getByTestId("file-input").setInputFiles(SAMPLE);
  await ann.getByRole("button", { name: "Analyze serve" }).click();
  await expect(ann.getByRole("heading", { name: "Coaching feedback" })).toBeVisible({ timeout: 4 * 60_000 });
  const analysisUrl = new URL(ann.url()).pathname;
  await ann.getByRole("button", { name: "Send to a friend" }).click();
  await ann.getByRole("button", { name: /Bob Share/ }).click();
  await expect(ann.getByRole("status").filter({ hasText: "Sent to Bob Share." })).toBeVisible();

  // Bob opens it from the message: read-only, named by Ann, no note or filename.
  await bob.goto("/messages");
  await bob.getByRole("link", { name: /Ann Share/ }).click();
  await bob.getByRole("link", { name: /Open their serve from/ }).click();
  await expect(bob).toHaveURL(new RegExp(`${analysisUrl}$`));
  await expect(bob.getByRole("heading", { level: 1, name: "Ann Share's serve" })).toBeVisible();
  await expect(bob.getByText("Shared by Ann Share")).toBeVisible();
  await expect(bob.getByRole("heading", { name: "Coaching feedback" })).toBeVisible();
  await expect(bob.getByText("sample_serve.mp4")).toHaveCount(0);
  await expect(bob.getByRole("button", { name: /Delete/ })).toHaveCount(0);
  await expect(bob.getByRole("button", { name: "This result looks wrong?" })).toHaveCount(0);
  await expectAccessible(bob, "a serve a friend sent you");
  // He has no serves of his own to compare with yet.
  await bob.getByRole("button", { name: "Compare with one of my serves" }).click();
  await expect(bob.getByText("You don't have a finished serve yet.")).toBeVisible();
  // The owner-only parts refuse him, through the API too.
  const id = analysisUrl.split("/").pop();
  expect((await bob.request.get(`/api/analyses/${id}/report`)).status()).toBe(404);
  expect((await bob.request.delete(`/api/analyses/${id}`)).status()).toBe(404);

  // Ann deletes the message: Bob can't open the serve any more.
  await ann.goto("/messages");
  await ann.getByRole("link", { name: /Bob Share/ }).click();
  const thread = ann.getByRole("region", { name: "Messages with Bob Share" });
  await thread.getByRole("button", { name: "Delete" }).click();
  await thread.getByRole("button", { name: "Yes, delete it" }).click();
  await expect(thread.getByText("Message deleted")).toBeVisible();
  await bob.reload();
  await expect(bob.getByRole("heading", { name: /couldn't find|not found/i })).toBeVisible();
  expect((await bob.request.get(`/api/analyses/${id}/result`)).status()).toBe(404);

  for (const page of [ann, bob]) {
    await deleteAccount(page);
    await page.context().close();
  }
});

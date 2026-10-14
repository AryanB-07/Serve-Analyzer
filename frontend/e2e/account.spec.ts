/** Changing your email through the Mailpit inbox, and downloading your data, through the real stack. */
import { readFile } from "node:fs/promises";

import { expect, test } from "./fixtures";

import { deleteAccount, emailedLink, newEmail, PASSWORD, signUpAndVerify, subjectsFor } from "./helpers";

test("changing your email takes the link sent to the new address", async ({ page }) => {
  const oldEmail = newEmail("old");
  const nextEmail = newEmail("new");
  await signUpAndVerify(page, oldEmail);

  await page.goto("/account");
  await page.getByRole("button", { name: "Change your email" }).click();
  await page.getByLabel("New email").fill(nextEmail);
  await page.getByLabel("Current password").fill(PASSWORD);
  await page.getByRole("button", { name: "Send confirmation link" }).click();
  await expect(page.getByRole("status")).toContainText(`We sent a link to ${nextEmail}`);

  // Nothing changes until the link is opened.
  await page.reload();
  await expect(page.getByText(oldEmail).first()).toBeVisible();

  await page.goto(await emailedLink(page.request, nextEmail, "/confirm-email"));
  await expect(page.getByRole("heading", { name: "Email changed" })).toBeVisible();
  await expect(page.getByText(nextEmail).first()).toBeVisible();
  await expect.poll(() => subjectsFor(page.request, oldEmail)).toContain("Your Serve Analyzer email was changed");

  // Signing in now takes the new address.
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByLabel("Email").fill(oldEmail);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toContainText("Incorrect email or password.");
  await page.getByLabel("Email").fill(nextEmail);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Analyze your serve" })).toBeVisible();

  await deleteAccount(page);
});

test("download my data saves a JSON file of the account", async ({ page }) => {
  const email = newEmail("export");
  await signUpAndVerify(page, email);
  await page.goto("/account");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download my data" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/^serve-analyzer-data-\d{4}-\d{2}-\d{2}\.json$/);
  const data = JSON.parse(await readFile(await file.path(), "utf8"));
  expect(data.account).toMatchObject({ email, email_verified: true });
  expect(data.analyses).toEqual([]);
  await expect(page.getByRole("status")).toContainText("Downloaded 0 analyses.");
  await deleteAccount(page);
});

test("asking for a password reset confirms it was sent, and the link sets a new password", async ({ page }) => {
  const email = newEmail("reset");
  await signUpAndVerify(page, email);
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.getByRole("link", { name: "Forgot your password?" }).click();
  await expect(page.getByRole("heading", { name: "Reset your password" })).toBeVisible();
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();

  await page.goto(await emailedLink(page.request, email, "/reset-password"));
  await page.getByLabel("New password").fill("a brand new end to end password");
  await page.getByRole("button", { name: "Set new password" }).click();
  await expect(page.getByRole("heading", { name: "Password changed" })).toBeVisible();

  await page.getByRole("link", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("a brand new end to end password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Analyze your serve" })).toBeVisible();
  const res = await page.request.delete("/api/auth/me", { data: { password: "a brand new end to end password" } });
  expect(res.status()).toBe(204);
});

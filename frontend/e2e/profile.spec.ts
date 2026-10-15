/** Profile and Settings through the real stack: a username, a name, a bio, a photo, and a new password. */
import { expect, test } from "./fixtures";

import { deleteAccount, newEmail, PASSWORD, signOut, signUpAndVerify } from "./helpers";

const PHOTO = new URL("../../tests/fixtures/profile_photo.png", import.meta.url).pathname;
const NEW_PASSWORD = "a fresh end to end passphrase";

test("filling in a profile, adding a photo and changing the password", async ({ page, browser, baseURL }) => {
  const email = newEmail("profile");
  const username = `e2e_${Date.now().toString(36)}`.slice(0, 20);
  const first = await signUpAndVerify(page, email);  // the username chosen at signup

  // A new account's profile has its username, and asks for the rest.
  await page.getByRole("button", { name: "Your account" }).click();
  await page.getByRole("link", { name: "Profile" }).click();
  await expect(page.getByRole("heading", { level: 1, name: `@${first}` })).toBeVisible();
  await expect(page.getByText("No bio yet.")).toBeVisible();
  await expect(page.getByText("Serves analyzed")).toBeVisible();

  // Settings: name, a new username (checked as it's typed) and bio.
  await page.getByRole("link", { name: "Edit profile" }).click();
  await expect(page).toHaveURL(/\/settings#profile$/);
  const profile = page.getByRole("form", { name: "Profile" });
  await profile.getByLabel("Display name").fill("End To End");
  await profile.getByLabel("Username").fill("ab");
  await expect(profile.getByText("Usernames are 3 to 20 characters.")).toBeVisible();
  await profile.getByLabel("Username").fill(username.toUpperCase());
  await expect(profile.getByText(`@${username} is available.`)).toBeVisible();
  await profile.getByLabel("Bio").fill("Serving from the deuce side.\nWorking on the toss.");
  await profile.getByRole("button", { name: "Save profile" }).click();
  await expect(profile.getByRole("status")).toHaveText("Profile saved.");

  // Someone else can't take it.
  const other = await (await browser.newContext({ baseURL, ignoreHTTPSErrors: true })).newPage();
  await signUpAndVerify(other, newEmail("profile-other"));
  await other.goto("/settings");
  const theirs = other.getByRole("form", { name: "Profile" });
  await theirs.getByLabel("Username").fill(username);
  await expect(theirs.getByText("That username is taken.")).toBeVisible();
  await deleteAccount(other);
  await other.context().close();

  // The profile shows it, and takes a photo: a PNG, cropped and converted in the browser.
  await page.getByRole("link", { name: "View profile" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "End To End" })).toBeVisible();
  await expect(page.getByText(`@${username}`)).toBeVisible();
  await expect(page.getByText("Working on the toss.")).toBeVisible();
  await page.getByTestId("avatar-input").setInputFiles(PHOTO);
  await expect(page.getByRole("button", { name: "Change photo" })).toBeVisible();
  const photo = page.locator("main img").first();
  await expect.poll(() => photo.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth)).toBe(512);
  expect(await photo.evaluate((img: HTMLImageElement) => img.naturalHeight)).toBe(512);
  // The header's account button shows it too.
  await expect(page.getByRole("button", { name: "Your account" }).locator("img")).toBeVisible();

  // The data download has the profile.
  const data = await (await page.request.get("/api/auth/me/export")).json();
  expect(data.profile).toMatchObject({ username, display_name: "End To End" });
  expect(data.profile.avatar).toBeTruthy();

  // A new password: this device stays signed in, another one is signed out.
  const otherDevice = await browser.newContext({ baseURL, ignoreHTTPSErrors: true });
  const login = await otherDevice.request.post("/api/auth/login", { data: { email, password: PASSWORD } });
  expect(login.status()).toBe(200);
  await page.goto("/settings");
  const password = page.getByRole("form", { name: "Change your password" });
  await password.getByLabel("Current password").fill(PASSWORD);
  await password.getByLabel("New password").fill(NEW_PASSWORD);
  await password.getByRole("button", { name: "Change password" }).click();
  await expect(password.getByRole("status")).toContainText("Every other device has been signed out.");
  expect((await otherDevice.request.get("/api/auth/me")).status()).toBe(401);
  await otherDevice.close();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();

  await signOut(page);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(NEW_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Analyze your serve" })).toBeVisible();

  const res = await page.request.delete("/api/auth/me", { data: { password: NEW_PASSWORD } });
  expect(res.status()).toBe(204);
});

test("old addresses still work: /history and /account", async ({ page }) => {
  await signUpAndVerify(page, newEmail("moved"));
  await page.goto("/history?score=good");
  await expect(page).toHaveURL(/\/serves\?score=good$/);
  await expect(page.getByRole("heading", { level: 1, name: "My Serves" })).toBeVisible();
  await page.goto("/account");
  await expect(page).toHaveURL(/\/settings$/);
  await deleteAccount(page);
});

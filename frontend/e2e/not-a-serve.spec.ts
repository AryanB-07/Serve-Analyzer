/**
 * Uploading a clip that isn't a serve, through the real stack: the worker runs the actual pipeline
 * on it, rejects it, and the browser shows why, with a way to say it was a serve.
 */
import { expect, test } from "./fixtures";

import { deleteAccount, newEmail, signUpAndVerify } from "./helpers";

// The sample serve's first frame held for 3 s: the player never swings (tests/fixtures/ATTRIBUTION.md).
const STILL_CLIP = new URL("../../tests/fixtures/standing_still.mp4", import.meta.url).pathname;

test("a clip that isn't a serve is rejected with a reason, and can be disputed", async ({ page }) => {
  await signUpAndVerify(page, newEmail("not-a-serve"));

  await page.getByRole("link", { name: "Analyze a serve" }).click();
  // First visit: the walkthrough points to the filming guide.
  await expect(page.getByRole("heading", { name: /Your first analysis in three steps/ })).toBeVisible();
  await page.getByRole("button", { name: "Show me how to film it" }).click();
  await expect(page.getByRole("region", { name: "How to film your serve" })).toBeFocused();
  await page.getByRole("button", { name: "Got it" }).click();
  await expect(page.getByRole("heading", { name: /three steps/ })).toBeHidden();

  // Dismissed, but the guide is still under the ? button.
  await page.getByRole("button", { name: "Help" }).click();
  await page.getByRole("dialog", { name: "Help" }).getByRole("tab", { name: "How to film your serve" }).click();
  await expect(page.getByRole("tabpanel").getByRole("img", { name: /Camera placement/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(page.getByRole("button", { name: "Help" })).toBeFocused();

  // The radio itself is visually hidden; its label is the button people click.
  await page.getByText("Right-handed", { exact: true }).click();
  await expect(page.getByLabel("Right-handed")).toBeChecked();
  await page.getByTestId("file-input").setInputFiles(STILL_CLIP);
  await expect(page.getByText("standing_still.mp4")).toBeVisible();
  await page.getByRole("button", { name: "Analyze serve" }).click();

  await expect(page).toHaveURL(/\/analyses\/[0-9a-f]{32}$/);
  const failure = page.getByRole("alert");
  await expect(failure.getByRole("heading", { name: "This doesn't look like a serve" })).toBeVisible({ timeout: 4 * 60_000 });
  await expect(failure).toContainText("We couldn't find a swing that reaches above the head.");
  await expect(failure).toContainText("Forehands, backhands and smashes can't be analysed yet.");
  await expect(failure.getByRole("link", { name: "Read the filming guide" })).toBeVisible();

  await failure.getByRole("button", { name: "This was a serve? Tell us" }).click();
  await expect(page.getByLabel("This was a serve")).toBeChecked();
  await page.getByLabel(/Anything to add/).fill("e2e: it really was");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(/we've noted that/)).toContainText("this was a serve");

  // The report is stored on the server: it's still there after a reload.
  await page.reload();
  await expect(page.getByText(/we've noted that/)).toContainText("this was a serve");

  // And it shows up in history as failed.
  await page.getByRole("link", { name: "History" }).click();
  await expect(page.getByText("standing_still.mp4")).toBeVisible();

  await deleteAccount(page);
});

/** The public sample analysis, signed out, in a real browser against the production build. */
import { expect, test } from "./fixtures";

test("anyone can open the sample analysis from the sign-in page and play it", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("link", { name: "see a sample analysis" }).click();
  await expect(page).toHaveURL(/\/demo$/);
  await expect(page.getByRole("heading", { name: "Sample analysis" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Coaching feedback" })).toBeVisible();

  // The video really loads (from the site's own files) and the shortcuts work.
  const video = page.locator("video").first();
  await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.readyState)).toBeGreaterThanOrEqual(2);
  expect(await video.evaluate((v: HTMLVideoElement) => v.duration)).toBeGreaterThan(4);
  await page.locator("main").click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("3");
  await expect(page.getByText(/Frame 12\d \/ 125/)).toBeVisible();

  // Simple by default; advanced shows the exact angles and confidence, and is remembered.
  await expect(page.getByRole("radio", { name: "Simple" })).toBeChecked();
  await expect(page.getByTestId("overall-score")).toHaveText(/^\d+$/);
  await expect(page.getByText("Angles over time")).toHaveCount(0);
  await page.getByText("Advanced", { exact: true }).click();
  await expect(page.getByText("Angles over time")).toBeVisible();
  await expect(page.getByTestId("confidence").first()).toContainText("Likely range");
  await page.reload();
  await expect(page.getByRole("radio", { name: "Advanced" })).toBeChecked();
  await page.getByText("Simple", { exact: true }).click();

  await expect(page.getByRole("button", { name: /Delete/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "This result looks wrong?" })).toHaveCount(0);
  await page.getByRole("link", { name: "Create a free account" }).click();
  await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible();
});

/** The help dialog in a real browser: open from any page, link to a topic, close with Back. */
import { expect, test } from "./fixtures";

test("help opens from the header, even signed out, and Back closes it", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByRole("button", { name: "Help" }).click();
  const dialog = page.getByRole("dialog", { name: "Help" });
  await expect(dialog.getByRole("tab", { name: "Getting started" })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(dialog.getByRole("tab", { name: "How to film your serve" })).toHaveAttribute("aria-selected", "true");
  await expect(page).toHaveURL(/[?&]help=filming/);

  // The page behind can't be reached while it's open: it's inert, and Tab stays in the dialog.
  await expect(page.locator("[inert]")).toContainText("Pick up where you left off");
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press("Tab");
    expect(await page.evaluate(() => Boolean(document.activeElement?.closest('[role="dialog"]')))).toBe(true);
  }

  await page.goBack();
  await expect(dialog).toBeHidden();
  await expect(page).toHaveURL(/\/login$/);
});

test("a link can open help at a topic", async ({ page }) => {
  await page.goto("/login?help=limits");
  await expect(page.getByRole("tab", { name: "What the analysis can't do" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tabpanel")).toContainText("It doesn't see the ball or racket");
  await page.getByRole("button", { name: "Close help" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
});

test("on a phone the dialog fits the screen and its topics scroll sideways", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login?help=filming");
  const box = await page.getByRole("dialog").boundingBox();
  expect(box).not.toBeNull();
  expect(box!.width).toBeLessThanOrEqual(390);
  expect(box!.height).toBeLessThanOrEqual(844);
  const pageWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(pageWidth).toBeLessThanOrEqual(390);
  await expect(page.getByRole("tabpanel").getByRole("img", { name: /Camera placement/ })).toBeVisible();
});

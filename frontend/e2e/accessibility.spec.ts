/**
 * Automated accessibility checks (axe-core, WCAG 2.1 A and AA) on every kind of page, in both
 * themes. Automated checks catch about a third of problems (contrast, labels, landmarks, ARIA
 * misuse); keyboard use is covered by the other specs.
 */
import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";
import { deleteAccount, newEmail, signUpAndVerify } from "./helpers";

const SAMPLE = new URL("../../tests/fixtures/sample_serve.mp4", import.meta.url).pathname;
const STILL_CLIP = new URL("../../tests/fixtures/standing_still.mp4", import.meta.url).pathname;

async function expectAccessible(page: Page, what: string) {
  for (const theme of ["dark", "light"] as const) {
    await page.evaluate((t) => { document.documentElement.dataset.theme = t; }, theme);
    // Let colour transitions finish, or the scan measures colours half-way between themes.
    // Only transitions: a spinner's animation never finishes.
    await page.evaluate(() =>
      Promise.all(document.getAnimations().filter((a) => a instanceof CSSTransition).map((a) => a.finished)),
    );
    const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    const summary = violations.map((v) => `${v.id} (${v.impact}): ${v.help} — ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(", ")}`);
    expect(summary, `${what}, ${theme} theme`).toEqual([]);
  }
}

test("signed-out pages", async ({ page }) => {
  for (const [path, heading] of [
    ["/login", "Sign in"], ["/signup", "Create your account"], ["/forgot-password", "Reset your password"],
    ["/privacy", "Privacy Policy"], ["/terms", "Terms of Service"], ["/demo", "Sample analysis"],
  ] as const) {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible();
    await expectAccessible(page, path);
  }
  await page.goto("/demo");
  await page.getByText("Advanced", { exact: true }).click();
  await expect(page.getByTestId("confidence").first()).toBeVisible();
  await expectAccessible(page, "/demo in advanced mode");
  await page.goto("/login?help=filming");
  await expect(page.getByRole("dialog", { name: "Help" })).toBeVisible();
  await expectAccessible(page, "the help dialog");
});

test("signed-in pages: upload, results, failure, history, account", async ({ page }) => {
  await signUpAndVerify(page, newEmail("a11y"));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /three steps/ })).toBeVisible();
  await expectAccessible(page, "upload page with the welcome card");

  await page.getByText("Right-handed", { exact: true }).click();
  await page.getByTestId("file-input").setInputFiles(SAMPLE);
  await page.getByText("Across the net", { exact: true }).click();
  await expectAccessible(page, "upload page with a file, hand and camera position chosen");
  await page.getByRole("button", { name: "Analyze serve" }).click();
  await expect(page.getByRole("heading", { name: "Coaching feedback" })).toBeVisible({ timeout: 4 * 60_000 });
  await expect(page.getByRole("region", { name: "Filmed from across the net" })).toBeVisible();
  await page.getByText("What this analysis can't do").click();
  await page.getByRole("button", { name: "This result looks wrong?" }).click();
  await expectAccessible(page, "results page with the report form open");

  await page.goto("/");
  await page.getByText("Right-handed", { exact: true }).click();
  await page.getByTestId("file-input").setInputFiles(STILL_CLIP);
  await page.getByRole("button", { name: "Analyze serve" }).click();
  await expect(page.getByRole("heading", { name: "This doesn't look like a serve" })).toBeVisible({ timeout: 4 * 60_000 });
  await expectAccessible(page, "the \"not a serve\" failure");

  await page.goto("/history");
  await expect(page.getByText("sample_serve.mp4")).toBeVisible();
  await expectAccessible(page, "history");

  await page.goto("/account");
  await page.getByRole("button", { name: "Change your email" }).click();
  await expectAccessible(page, "account page with the email form open");
  await deleteAccount(page);
});

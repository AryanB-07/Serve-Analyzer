/** A real serve analysed end to end: the results page, its known limits, and reporting a problem. */
import { expect, test } from "./fixtures";

import { deleteAccount, newEmail, signUpAndVerify } from "./helpers";

const SAMPLE = new URL("../../tests/fixtures/sample_serve.mp4", import.meta.url).pathname;

test("a serve's results show the limits and take a report", async ({ page }) => {
  await signUpAndVerify(page, newEmail("results"));
  await page.getByRole("link", { name: "Analyze a serve" }).click();
  await page.getByText("Right-handed", { exact: true }).click();
  await page.getByTestId("file-input").setInputFiles(SAMPLE);
  await page.getByRole("button", { name: "Analyze serve" }).click();

  await expect(page.getByRole("heading", { name: "Coaching feedback" })).toBeVisible({ timeout: 4 * 60_000 });
  await expect(page.getByRole("heading", { name: "sample_serve.mp4" })).toBeVisible();

  const limits = page.getByText("What this analysis can't do");
  await limits.click();
  await expect(page.getByText("It doesn't see the ball or racket")).toBeVisible();

  await page.getByRole("button", { name: "This result looks wrong?" }).click();
  await page.getByLabel("A phase is marked at the wrong moment").check();
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(/we've noted that/)).toContainText("a phase is marked at the wrong moment");

  // The report and the analysis are in the data download.
  const res = await page.request.get("/api/auth/me/export");
  const data = await res.json();
  expect(data.analyses).toHaveLength(1);
  expect(data.analyses[0]).toMatchObject({ status: "succeeded", report: { reason: "wrong_phases" } });
  expect(data.analyses[0].results.phases.contact).not.toBeNull();
  expect(Object.keys(data.analyses[0].files).sort()).toEqual(
    ["annotated_video", "frames", "original_video", "playback_video", "thumbnail"]);

  await deleteAccount(page);
});

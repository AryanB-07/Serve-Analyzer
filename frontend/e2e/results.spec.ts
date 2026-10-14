/** A real serve analysed end to end: the results page, its known limits, and reporting a problem. */
import { expect, test } from "./fixtures";

import { deleteAccount, newEmail, signUpAndVerify } from "./helpers";

const SAMPLE = new URL("../../tests/fixtures/sample_serve.mp4", import.meta.url).pathname;

test("a serve's results show the limits and take a report", async ({ page }) => {
  await signUpAndVerify(page, newEmail("results"));
  await page.getByRole("link", { name: "Analyze a serve" }).click();
  await page.getByText("Right-handed", { exact: true }).click();
  await page.getByTestId("file-input").setInputFiles(SAMPLE);
  // The sample clip really was filmed from across the net.
  await page.getByText("Across the net", { exact: true }).click();
  await expect(page.getByRole("radio", { name: "From across the net" })).toBeChecked();
  await page.getByRole("button", { name: "Analyze serve" }).click();

  await expect(page.getByRole("heading", { name: "Coaching feedback" })).toBeVisible({ timeout: 4 * 60_000 });
  await expect(page.getByRole("heading", { name: "sample_serve.mp4" })).toBeVisible();

  // What that position can't read is said, and the cards are marked.
  const note = page.getByRole("region", { name: "Filmed from across the net" });
  await expect(note).toContainText("the elbow bend at the trophy position can't be read from one camera");
  await expect(page.getByRole("article", { name: "Front knee bend" })).toContainText("approximate from this angle");
  await expect(page.getByText("Your hitting arm was hard to see around the trophy position")).toBeVisible();
  await note.getByRole("button", { name: "Where to put the camera" }).click();
  await expect(page.getByRole("tab", { name: "How to film your serve" })).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("Escape");

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
  expect(data.analyses[0]).toMatchObject({ status: "succeeded", camera_view: "front", report: { reason: "wrong_phases" } });
  expect(data.analyses[0].results.phases.contact).not.toBeNull();
  expect(Object.keys(data.analyses[0].files).sort()).toEqual(
    ["annotated_video", "frames", "original_video", "playback_video", "thumbnail"]);

  await deleteAccount(page);
});

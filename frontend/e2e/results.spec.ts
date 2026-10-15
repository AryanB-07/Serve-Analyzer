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
  // Simple mode (the default): scores out of 100, rough where the angle is approximate.
  const knee = page.getByRole("article", { name: "Front knee bend" });
  await expect(page.getByRole("radio", { name: "Simple" })).toBeChecked();
  await expect(page.getByRole("region", { name: "Serve score" })).toContainText("/ 100");
  await expect(knee).toContainText("rough from this angle");
  await expect(knee.getByRole("meter")).toHaveAttribute("aria-valuenow", /\d+/);
  // Advanced mode: the exact angle, its likely range and the tracking confidence.
  await page.getByText("Advanced", { exact: true }).click();
  await expect(knee).toContainText("approximate from this angle");
  await expect(knee).toContainText(/\d+\.\d°/);
  await expect(knee.getByTestId("confidence")).toContainText("Tracking confidence");
  await expect(knee.getByTestId("confidence")).toContainText("from your camera position");
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

  // History: the serve's score on its card, its key positions behind a button, and a note.
  await page.getByRole("link", { name: "History" }).click();
  const card = page.getByRole("article", { name: "sample_serve.mp4" });
  const score = Number(await card.getByTestId("history-score").textContent());
  expect(score).toBe(data.analyses[0].results.scores.overall);
  await expect(card.locator("time")).toBeVisible();
  await card.getByRole("button", { name: "Show details" }).click();
  await expect(card.getByRole("meter", { name: "Front knee bend score" })).toHaveAttribute("aria-valuenow", /\d+/);
  await card.getByRole("button", { name: "Add a note to sample_serve.mp4" }).click();
  await card.getByLabel("Note on sample_serve.mp4").fill("e2e: first session");
  await card.getByRole("button", { name: "Save note" }).click();
  await expect(card.getByTestId("history-note")).toHaveText("e2e: first session");

  // The filters run on the server: the serve's own band keeps it, another band hides it.
  const sidebar = page.getByRole("complementary", { name: "Filters" });
  const band = score >= 80 ? "80–100 · good" : score >= 50 ? "50–79 · borderline" : "0–49 · needs work";
  const other = score >= 80 ? "0–49 · needs work" : "80–100 · good";
  if (await sidebar.getByRole("button", { name: /^Filters/ }).isVisible()) await sidebar.getByRole("button", { name: /^Filters/ }).click();
  await sidebar.getByRole("radio", { name: band }).check();
  await expect(card).toBeVisible();
  await sidebar.getByRole("radio", { name: other }).check();
  await expect(page.getByText("No serves match these filters")).toBeVisible();
  await page.reload(); // the filters are in the URL
  await expect(sidebar.getByRole("radio", { name: other })).toBeChecked();
  await page.getByRole("region", { name: "Your serves" }).getByRole("button", { name: "Clear filters" }).click();
  await expect(card.getByTestId("history-note")).toHaveText("e2e: first session"); // saved on the server
  const exported = await (await page.request.get("/api/auth/me/export")).json();
  expect(exported.analyses[0].note).toBe("e2e: first session");

  await deleteAccount(page);
});

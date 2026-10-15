import AxeBuilder from "@axe-core/playwright";
import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const MAILPIT = process.env.MAILPIT_URL ?? "http://localhost:8025";
export const PASSWORD = "end to end password";

export function newEmail(tag: string): string {
  return `e2e-${tag}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}@example.com`;
}

interface MailpitSummary {
  ID: string;
}

/** The path and query of the newest link to ``path`` emailed to ``to`` (waits for it to arrive). */
export async function emailedLink(request: APIRequestContext, to: string, path: string): Promise<string> {
  let found: string | null = null;
  await expect
    .poll(
      async () => {
        const search = await request.get(`${MAILPIT}/api/v1/search`, { params: { query: `to:${to}` } });
        const { messages } = (await search.json()) as { messages: MailpitSummary[] };
        for (const { ID } of messages) {
          const message = (await (await request.get(`${MAILPIT}/api/v1/message/${ID}`)).json()) as { Text: string };
          const match = message.Text.match(new RegExp(`https?://[^\\s]+(${path}\\?token=[\\w-]+)`));
          if (match) {
            found = match[1]!;
            return true;
          }
        }
        return false;
      },
      { message: `an email to ${to} linking to ${path}`, timeout: 60_000, intervals: [1000] },
    )
    .toBe(true);
  return found!;
}

/** The subjects of every email sent to ``to``, newest first. */
export async function subjectsFor(request: APIRequestContext, to: string): Promise<string[]> {
  const search = await request.get(`${MAILPIT}/api/v1/search`, { params: { query: `to:${to}` } });
  const { messages } = (await search.json()) as { messages: { Subject: string }[] };
  return messages.map((m) => m.Subject);
}

/** Sign up through the form and confirm the address from the emailed link. */
export async function signUpAndVerify(page: Page, email: string): Promise<void> {
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Analyze your serve" })).toBeVisible();
  await page.goto(await emailedLink(page.request, email, "/verify-email"));
  await expect(page.getByRole("heading", { name: "Email confirmed" })).toBeVisible();
}

/** Delete the signed-in account, so test runs leave nothing behind. */
export async function deleteAccount(page: Page): Promise<void> {
  const res = await page.request.delete("/api/auth/me", { data: { password: PASSWORD } });
  expect(res.status()).toBe(204);
}

/** Sign out from the account menu in the header. */
export async function signOut(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Your account" }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
}

/** axe-core (WCAG 2.1 A and AA) finds nothing on the page, in both themes. */
export async function expectAccessible(page: Page, what: string) {
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

/**
 * The browser tests' `test`: Playwright's, plus a check that the page never broke its
 * Content-Security-Policy (deploy/Caddyfile). A violation means something the app needs was
 * blocked, or something it shouldn't load was attempted. Every spec imports test from here.
 */
import { expect, test as base } from "@playwright/test";

export const test = base.extend<{ cspViolations: string[] }>({
  cspViolations: [
    async ({ page }, use) => {
      const violations: string[] = [];
      await page.exposeFunction("__reportCsp", (v: string) => violations.push(v));
      await page.addInitScript(() => {
        document.addEventListener("securitypolicyviolation", (e) => {
          (window as unknown as { __reportCsp: (v: string) => void }).__reportCsp(
            `${e.violatedDirective} blocked ${e.blockedURI || "inline"} on ${location.pathname}`,
          );
        });
      });
      await use(violations);
      expect(violations, "Content-Security-Policy violations").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };

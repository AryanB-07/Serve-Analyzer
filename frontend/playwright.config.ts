/**
 * Browser end-to-end tests against the real production stack: the built images, Postgres, the
 * worker running the actual pipeline, and a Mailpit inbox. Start it, then run the tests:
 *
 *   KEEP=1 E2E=0 ../scripts/smoke_docker.sh     # or plain scripts/smoke_docker.sh, which runs them too
 *   npm run test:e2e
 *
 * E2E_BASE_URL and MAILPIT_URL point elsewhere (defaults: the smoke stack's https://localhost:8443
 * and http://localhost:8025). Each test signs up a fresh account and deletes it at the end.
 *
 * Running the suite three or more times within 10 minutes against one stack trips the per-IP
 * sign-up limit ("Too many attempts"). Wait, or clear the counters:
 *   docker compose -p serve-smoke … exec postgres psql -U serve -d serve_analyzer -c "DELETE FROM auth_attempts"
 */
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  // A real analysis of a short clip takes well under a minute; CI machines can be slow.
  timeout: 5 * 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "https://localhost:8443",
    ignoreHTTPSErrors: true, // the smoke stack uses Caddy's self-signed certificate
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});

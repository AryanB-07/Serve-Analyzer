# Launch checklist

The goal is a consumer-ready product deployed on AWS. Tick items off as they're done.

## Done

- [x] Serve analysis pipeline, the multi-view evaluation, and tuning (`docs/tuning-results.md`)
- [x] Rejecting clips that aren't a serve (`docs/serve-check.md`)
- [x] Accounts: email verification, password reset, deleting an analysis, deleting an account
- [x] CI on GitHub Actions; the production images are built and smoke-tested end to end
- [x] Fits a small free-tier server: the API no longer loads MediaPipe (289 → 151 MB), and
      result videos are H.264 so browsers can play them (they weren't on Linux)
- [x] Privacy and legal:
  - Privacy Policy and Terms pages, and consent recorded at signup
  - original uploads deleted after 30 days
  - no request or IP logging, and container logs rotate

## Next phases (in order)

1. **Deploy on the AWS free tier** following `docs/deploy-aws-free-tier.md`, then run
   `scripts/smoke_test.py` against it and analyse a serve from your phone.
2. **Later, the full AWS setup** (`docs/deployment.md`):
   - a bigger EC2 instance, RDS Postgres, an S3 bucket and an IAM role;
   - smoke-test everything, including uploads from phones (portrait video, HEVC `.mov` from
     iPhones).
3. **Error tracking**: the uptime checks exist (`/api/health`, `/api/health/queue`); add
   exception reporting (e.g. Sentry's free tier) if you want stack traces from production.
4. **Launch.**

## Before launch (only you can do these)

- [ ] **A hostname:** a free DuckDNS subdomain for now (`docs/deploy-aws-free-tier.md`, step 2);
  buy a domain later.
- [ ] **Email:** a free Brevo account with one verified sender (step 3). Once you have a domain,
  switch to Resend or Brevo domain sending, add the DNS records (SPF, DKIM, DMARC), and test
  that emails don't land in spam.
- [ ] **Monitoring:** UptimeRobot (or similar) on `/api/health` and `/api/health/queue`, and an AWS
  zero-spend budget (step 6).
- [ ] **Backups:** the nightly database dump cron job (step 7).
- [ ] **Fill in the legal details** in `frontend/src/features/legal/config.ts`: operator name,
  contact email, governing law, hosting region.
- [ ] **Have the Privacy Policy and Terms reviewed** for where you operate. They're written to
  match exactly what the app does, but they aren't legal advice. Points to confirm:
  - the $50 liability cap;
  - the minimum age (13), including the digital-consent age in the EU and UK;
  - whether you need a cookie notice (the app uses only a sign-in cookie, so usually not).
- [ ] **Match the policy to the infrastructure:**
  - RDS backup retention = `backupRetentionDays` (7);
  - S3 versioning off;
  - `SERVE_API_UPLOAD_RETENTION_DAYS` = `uploadRetentionDays` (30).
- [ ] Generate `SERVE_API_SECRET` and keep it in the server's `deploy/.env` only.
- [ ] **Policy changes:** if you ever change the Privacy Policy or Terms materially, bump
  `TERMS_VERSION` (both places) and email users before the change takes effect. The policy
  promises this.

## Product polish (not blocking, but expected by users)

- [ ] Test the "this doesn't look like a serve" failure end to end in the UI.
- [ ] A first-visit walkthrough pointing to the filming guide.
- [ ] Show the known limits in the app: smashes and high-finish backhands can pass the serve check,
  a swing that misses the ball looks like a serve, and the analysis is from one camera.
- [ ] A "this result looks wrong" button. It's also the way to collect labelled clips for a
  trained serve classifier later.
- [ ] Self-serve "download my data". The Privacy Policy currently says to email for a copy.
- [ ] Changing your account's email address (not supported yet).

## Accuracy (optional)

- [ ] More real footage from your own players, especially slow motion and non-serves.
- [ ] Evaluate a second camera angle; the depth study says that, not tuning, is the next real
  accuracy gain.

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

- [x] The "this doesn't look like a serve" failure tested end to end in a real browser, against
      the production images (`frontend/e2e`, run by `scripts/smoke_docker.sh` and CI).
- [x] A first-visit walkthrough pointing to the filming guide.
- [x] A Help button (?) in the header on every page: getting started, the filming guide, the
      known limits and keyboard shortcuts. To add help for a new feature, add a topic to
      `HELP_TOPICS` in `frontend/src/features/help/topics.tsx`; links can open one with `?help=<id>`.
- [x] The known limits shown in the app, on the upload and results pages.
- [x] A "this result looks wrong" button, and "this was a serve" on a `NOT_A_SERVE` failure.
      List the reports with `python -m serve_api.reports` (`docs/deployment.md`).
- [x] Self-serve "download my data" on the account page.
- [x] Changing your account's email address, confirmed from a link sent to the new address.
- [ ] **Review the reports** every week or two after launch. Disputed `NOT_A_SERVE` failures and
  "this isn't a serve" reports are the serve check's mistakes. Their original videos are deleted
  30 days after upload, so look at them before then.
- [ ] **If you want to train a model on reported clips,** change the Privacy Policy first. It
  currently promises that videos aren't used to train machine-learning models. That's a material
  change: ask for opt-in consent, bump `TERMS_VERSION` and email users.

## Hardening

- [x] Video limits enforced on the server: over 15 s refused before any conversion, over 120 fps
      reduced to 120, over 1920 px scaled down (`docs/file-formats.md`)
- [x] Security review of the API and proxy. Fixed:
  - a strict Content-Security-Policy, with the inline script moved out to allow it;
  - a 1 MB limit on JSON request bodies;
  - the API docs hidden outside development;
  - Permissions-Policy and Cross-Origin-Opener-Policy headers.
  Dependencies: `pip-audit` found nothing; `npm audit` found one build-time issue, now updated.
- [x] Accessibility: axe-core scans every page type in both themes on every push (WCAG 2.1 AA).
      Fixed the low contrast of button text and the phase timeline's labels in the dark theme.
- [x] One-command server setup (`scripts/server_setup.sh`), tested in a fresh Ubuntu container
- [x] Backup and restore scripts, with a restore tested on every push
- [x] Existing data checked: seed accounts with awkward rows (`scripts/seed_dev_data.py`), and a
      checker that loads every account and analysis in a database through the API
      (`scripts/check_dev_data.py`). Fixed along the way:
  - an unknown error code on one failed analysis made the whole History list fail;
  - the header scrolled sideways on phones;
  - a page that crashed showed React Router's developer screen; it now shows a friendly error
    page inside the app.
- [ ] **Before each deploy with a migration:** load the latest backup into a scratch Postgres
  (`gunzip -c db-….sql.gz | psql <scratch url>`) and run `scripts/check_dev_data.py` with
  `SERVE_API_DATABASE_URL` pointing at it. It migrates the copy, and only the copy is written to.
  Not `scripts/restore_db.sh`, which restores over the live database.

## Portfolio and operations

- [x] A public demo at `/demo`: a real analysis of the sample clip, no account needed, linked from
      the sign-in and sign-up pages. Put `https://<your host>/demo` in the README and on your CV.
- [x] A decision log (`docs/decisions.md`): each major choice, what else was considered, and the
      evidence. Interview preparation.
- [x] Architecture diagrams in the README (Mermaid, which GitHub draws).
- [x] Costs: no paid APIs; every outside service and its free plan in `docs/costs.md`.
- [x] Optional error reporting (Sentry's free plan or GlitchTip), off until configured.
- [ ] **If you turn on error reporting:** sign up for Sentry's free Developer plan (or GlitchTip),
  put the DSN in `deploy/.env` as `SERVE_API_SENTRY_DSN`, set `errorReporting: true` in
  `frontend/src/features/legal/config.ts`, and bump `TERMS_VERSION` and `LAST_UPDATED`.
- [x] Screenshots of the demo in the README (`docs/images`).

## Results views

- [x] Simple mode (scores out of 100, an overall serve score, plain feedback) and advanced mode
      (exact angles, tracking confidence, tracking noise, camera error, likely range). The choice
      is remembered per browser.
- [ ] **Validate the reference ranges** before leaning on the scores. They're placeholders
  (`serve_analyzer/data/reference_ranges.json`), and simple mode turns them into grades.
- [x] Profile and Settings: username, display name, bio and picture (metadata stripped),
      serve stats, and a password change that signs out other devices.
- [x] Friends: requests, friendships and blocks, found by exact username only; non-friends see
      a name and picture, friends also see the bio.
- [x] Sharing with friends: serve stats, key positions and a friends leaderboard, each opt-in.
- [x] Messages between friends, with read state, deleting, reporting and blocking.
- [x] Sending serves to friends (read-only, ends with the message or the friendship), and comparing with a friend's serve.
- [ ] **After launch, weekly:** review reports of people and messages
  (`docker compose -f deploy/docker-compose.yml exec api python -m serve_api.reports --people`), and act
  on them with `python -m serve_api.moderate show|suspend|unsuspend <username>`.
- [ ] **Before leaning on ranks:** validate the reference ranges. The leaderboard makes the scores
  more visible, and every score shown to friends says the ranges aren't validated yet.
- [x] A released username is held for its owner for 30 days, so nobody can impersonate a renamed player.
- [x] Notifications (new followers, follow-backs, serves sent to you) and account suspension.
- [x] History (now My Serves): score cards with upload time, optional notes, key-position details, and
      server-side filters by time, score and key position.

## Camera position

- [x] Automatic view detection evaluated: it missed its targets (`docs/view-detection.md`), so the
      app asks "Where was your camera?" at upload, optionally.
- [x] With an answer, measurements are rated measured, approximate or "can't be read from this
      angle" by the rig's error for that position, against each measurement's good range.
- [x] A hidden-arm note when the hitting arm is mostly out of sight at the trophy position.
- [ ] **Review the open questions** in `docs/view-detection.md`. The rig rates the behind and
  back-corner views as well as side-on, and its ratings assume its own stance.
- [ ] **Once real answers come in:** compare people's stated camera positions against the
  problem reports, to check the ratings.

## Video formats

- [x] MOV, MP4/M4V, WebM, MKV, AVI, 3GP and MTS tested across 160 variant runs, with
      rotation, interlacing, stretched pixels, AV1, high frame rates and broken files handled
      (`docs/file-formats.md`)
- [ ] **Record two or three serves on your iPhone with HDR on** (the camera's default) and add
  them to the evaluation clips. HDR footage is analysed without tone mapping today, and
  synthetic HDR wasn't realistic enough to tune it.

## Accuracy (optional)

- [ ] More real footage from your own players, especially slow motion and non-serves.
- [ ] Evaluate a second camera angle; the depth study says that, not tuning, is the next real
  accuracy gain.

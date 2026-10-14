# Costs and outside services

Serve Analyzer uses no paid APIs. The analysis runs on the server itself (MediaPipe on the CPU),
so no video or image is ever sent to an AI service, and nothing is billed per analysis. This page
lists every outside service the code or the deploy guides touch. The audit covered the code,
configuration, scripts, evaluation tools and dependencies; the last one was in October 2026.

## What the running app talks to

| Service | What for | Required? | Cost |
|---|---|---|---|
| **AWS EC2** (one t3.small or t3.micro) | The server | Yes, or any x86 Linux server | Free on the AWS free plan or credits (`docs/deploy-aws-free-tier.md`); about $15 a month for a t3.small after that |
| **Brevo** (SMTP) | Account emails: confirmation, password reset, email change | Yes, or any SMTP server | Free plan: 300 emails a day |
| **DuckDNS** | A free hostname, so HTTPS works without buying a domain | Until you buy a domain | Free |
| **Let's Encrypt**, through Caddy | HTTPS certificates | Yes (automatic) | Free |
| **Google's model storage** (`storage.googleapis.com`) | Downloading MediaPipe's pose model, once, the first time the worker runs | Yes (automatic) | Free, no key |
| **Sentry** or **GlitchTip** | Error reports | No: off unless `SERVE_API_SENTRY_DSN` is set | Sentry's Developer plan is free (5,000 errors a month); GlitchTip is open source and free to self-host |
| **AWS S3** | Storing videos | No: videos are on the server's disk by default (`SERVE_API_STORAGE=local`) | Only if you switch to it: 5 GB free for 12 months on the old free tier, then about $0.023 per GB a month |

The browser loads nothing from other companies: no fonts, analytics, maps or tracking. The
Content-Security-Policy enforces that.

## Used for building, testing and monitoring

| Service | What for | Cost |
|---|---|---|
| **GitHub** and **GitHub Actions** | Code hosting and CI | Free for public repositories |
| **Docker Hub** images (`python`, `node`, `caddy`, `postgres`, `mailpit`) and **mwader/static-ffmpeg** | Building and testing | Free |
| **npm** and **PyPI** packages | Dependencies: all open source (MIT, BSD, Apache), none needs a key | Free |
| **UptimeRobot** (or Better Stack) | Uptime monitoring of `/api/health` | Free plan |
| **Wikimedia Commons** and **Pexels** | The evaluation clips (`evaluation/labels/`), downloaded by `python -m evaluation.real fetch` | Free, no key |

## Paid things deliberately not used

- **Hosted pose or vision APIs** (Google Cloud Vision, AWS Rekognition and the like) would bill per
  video, and would send users' videos to a third party, which the Privacy Policy rules out.
- **Managed queues and caches** (SQS, ElastiCache, Redis Cloud): the job queue is a table in
  Postgres (`docs/decisions.md`, decision 10).
- **Managed databases** (RDS): optional for later. The free-tier setup runs Postgres in a
  container, with the nightly backup script.
- **Transactional email platforms' paid tiers**: 300 emails a day covers sign-ups and resets for
  a small launch.

## What would start costing money

- More than one small server, or keeping the server after the free plan or credits run out.
- More than 300 emails a day: Brevo's paid plans, or a domain with Resend (free for 3,000 a month).
- Storing videos in S3 beyond the free allowance, or EBS snapshots beyond it.

An AWS zero-spend budget (step 6 of `docs/deploy-aws-free-tier.md`) emails you as soon as
anything costs money.

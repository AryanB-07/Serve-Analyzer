# Deploying Serve Analyzer

This runs the whole app on one Linux server with Docker, with the database and video
storage on managed services. Expect about an hour the first time.

```
            HTTPS
browser ───────────► Caddy (web) ──/api──► API (api) ──► Postgres (managed)
   │                  └── the built frontend      │
   │ presigned PUT/GET                            └──► job queue in Postgres ◄── workers (worker × N)
   └────────────────► S3 bucket ◄───────────────────────────────────────────────┘
```

Everything is in `deploy/`: `docker-compose.yml`, the `Caddyfile` and `.env.example`. The
images are built from the `Dockerfile` in the repository root.

## 1. What you need

- **A Linux server** with Docker and the Compose plugin. Pose extraction is CPU-bound: plan for
  about 1 CPU core and 1.5 GB of RAM per worker, plus 1 GB for everything else. 4 cores and 8 GB
  runs 2 to 3 workers comfortably.
- **A domain name** with an `A` (and `AAAA`, if you have IPv6) record pointing at the server.
  Ports 80 and 443 must be open. Caddy uses them to get and renew the HTTPS certificate.
- **Postgres 14 or newer**, preferably managed (AWS RDS, Neon, Supabase, DigitalOcean), with
  automated backups and point-in-time recovery turned on. Create an empty database. The app
  creates its tables itself.
- **An S3 bucket**, or an S3-compatible service such as Cloudflare R2 or MinIO, plus credentials
  that can read, write, list and delete in it.

## 2. Set up the bucket

Block all public access; the app only uses short-lived presigned URLs. Browsers upload straight
to the bucket, so it needs a CORS rule allowing your domain:

```json
[
  {
    "AllowedOrigins": ["https://serve.example.com"],
    "AllowedMethods": ["PUT", "GET"],
    "AllowedHeaders": ["Content-Type", "Range"],
    "ExposeHeaders": ["Content-Length", "Content-Range", "Accept-Ranges"],
    "MaxAgeSeconds": 3600
  }
]
```

With the AWS CLI: `aws s3api put-bucket-cors --bucket <name> --cors-configuration file://cors.json`
(the file wraps the list in `{"CORSRules": [...]}`).

The credentials need `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject` and `s3:ListBucket` on
the bucket. An IAM role attached to the server works instead of access keys.

**Leave versioning off** (the default). The app deletes videos when people delete an analysis or
their account, and deletes original uploads after `SERVE_API_UPLOAD_RETENTION_DAYS` (30). With
versioning on, those deletions would only hide the files, and the Privacy Policy would be wrong.
If you want versioning as protection against mistakes, add a lifecycle rule that permanently
deletes noncurrent versions after at most as many days as `backupRetentionDays` in the policy
(7).

The app removes original uploads itself. An S3 lifecycle rule expiring `uploads/` after 31 days
is an optional safety net.

## 3. Configure

```bash
git clone https://github.com/AryanB-07/Serve-Analyzer.git
cd Serve-Analyzer
cp deploy/.env.example deploy/.env
```

Fill in `deploy/.env`:

| Variable | What to put |
|---|---|
| `DOMAIN` | Your hostname, e.g. `serve.example.com` |
| `SERVE_API_SECRET` | A long random string: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`. Keep it stable, because changing it invalidates outstanding upload links. |
| `SERVE_API_DATABASE_URL` | `postgresql://user:password@host:5432/dbname` (add `?sslmode=require` if your provider needs it) |
| `SERVE_API_STORAGE` | `s3` |
| `SERVE_API_S3_BUCKET`, `SERVE_API_S3_REGION` | Your bucket and its region |
| `SERVE_API_S3_ENDPOINT_URL` | Only for R2, MinIO and similar services |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | The bucket credentials (omit if using an instance role) |
| `WORKERS` | How many analyses can run at once (one per worker) |
| `SERVE_API_APP_URL` | `https://` plus your domain. Links in emails point here. |
| `SERVE_API_SMTP_HOST`, `SERVE_API_SMTP_PORT` | Your mail server, e.g. `smtp.gmail.com` and `587` (see "Email" below) |
| `SERVE_API_SMTP_USERNAME`, `SERVE_API_SMTP_PASSWORD` | The sending account and its password (for Gmail, an app password) |
| `SERVE_API_EMAIL_FROM` | Optional From address; defaults to the SMTP username |
| `SERVE_API_UPLOAD_RETENTION_DAYS` | Days to keep original uploads (default 30; `0` keeps them). Must match `uploadRetentionDays` in the Privacy Policy config. |

The API and workers refuse to start outside development if `SERVE_API_SECRET` is empty or the
development value, if no SMTP host is set, or if `SERVE_API_APP_URL` still points at localhost.

### Email

The app sends four emails: a link to confirm the address after signing up, a password-reset
link, and notices when a password is changed or an account is deleted. People must confirm
their email before they can analyse a serve (turn this off with
`SERVE_API_REQUIRE_VERIFIED_EMAIL=0`).

**Sending through a Gmail account:**

1. Turn on 2-Step Verification for the Google account.
2. Create an app password at https://myaccount.google.com/apppasswords and copy the 16
   characters.
3. Set `SERVE_API_SMTP_HOST=smtp.gmail.com`, `SERVE_API_SMTP_PORT=587`,
   `SERVE_API_SMTP_USERNAME` to the Gmail address, and `SERVE_API_SMTP_PASSWORD` to the app
   password.

Gmail caps how much a personal account can send, roughly 500 messages a day. Each address can
request at most 3 emails an hour. Gmail also rewrites the From address to the account unless it
is one of the account's verified "Send mail as" addresses. That is fine to launch with. When
volume grows, switch to a transactional provider (Amazon SES, Postmark, Resend): only the
`SMTP_*` values change.

In development, with no SMTP host, emails aren't sent. Each one is written to
`var/outbox/*.eml`, and its text, including the link, is printed in the API log.

## 4. Start it

```bash
docker compose -f deploy/docker-compose.yml up -d --build
docker compose -f deploy/docker-compose.yml ps        # api should become "healthy"
curl https://serve.example.com/api/health              # {"status":"ok"}
```

On first start, the API creates the database tables. It holds a Postgres lock while doing this,
so it's safe with several API containers. Workers wait until the API is healthy. Then open the
site and create an account.

## 5. Running it

- **Update:** `git pull && docker compose -f deploy/docker-compose.yml up -d --build`. Database
  migrations run automatically when the new API starts. Jobs that were mid-analysis when a
  worker was replaced are picked up again within about 2 minutes.
- **Scale workers:** change `WORKERS` in `deploy/.env` and rerun `up -d`, or run
  `docker compose -f deploy/docker-compose.yml up -d --scale worker=4`. Workers on other
  machines work too, as long as they use the same database and bucket.
- **Logs:** `docker compose -f deploy/docker-compose.yml logs -f api worker`. Worker lines
  worth alerting on: `requeued … whose worker stopped responding` and `failed … after 3 attempts`.
- **Health:** point an uptime monitor at `https://<domain>/api/health`. It returns 503 if the
  database can't be reached.
- **Backups:** your managed Postgres handles the database. Keep its automated backup retention
  equal to `backupRetentionDays` in `frontend/src/features/legal/config.ts` (RDS defaults to 7
  days), because the Privacy Policy states that number. For the bucket, see the versioning note
  in step 2.
- **Limits:** `SERVE_API_DAILY_ANALYSIS_LIMIT` and `SERVE_API_MAX_ACTIVE_ANALYSES` control each
  user's budget.

## Without S3 or managed Postgres

For a small, single-server install, set `SERVE_API_STORAGE=local` to keep videos in a Docker
volume shared by the API and workers. Add `--profile bundled-db` to run Postgres in a container,
with `SERVE_API_DATABASE_URL=postgresql://serve:<POSTGRES_PASSWORD>@postgres:5432/serve_analyzer`.
You're then responsible for backing up the `objects` and `postgres-data` volumes, and all workers
must run on this server.

## What was and wasn't tested

The S3 backend is tested against a local S3-compatible server (moto), including the full
upload → analysis → playback flow. The Caddy configuration is tested by running Caddy in front
of the app and driving it in a browser. The Docker images and the compose stack haven't been
built as part of the test suite: build and smoke-test them (steps 4 and 5) on a staging
server before sending real users to it.

# Deploying on the AWS free tier

This guide runs the whole app on one small EC2 instance, with no domain and no email provider
to pay for. It takes about an hour the first time. `docs/deployment.md` covers the general
setup (managed Postgres, S3, more workers) once you outgrow this.

```
browser ──HTTPS──► EC2 instance (Docker): Caddy ─► API ─► Postgres (in a container)
                                                   └──► worker (MediaPipe) ─► videos on the disk
```

## What fits, measured

These are the production containers analysing a 1080p, 15-second serve on Linux. The numbers
are peak memory:

| Process | Memory |
|---|---|
| Worker: MediaPipe heavy model, pose for every frame | about 705 MB |
| ffmpeg, re-encoding the two result videos to H.264 (briefly, while the worker waits) | about 565 MB |
| API, one process (it never loads MediaPipe) | about 160 MB |
| Postgres | about 30–60 MB |
| Caddy (HTTPS and the website) | about 20 MB |

So the peak is about 1.5 GB for a few seconds per analysis, and around 300 MB when idle.

- **t3.small (2 GB):** fits, with a swap file as a safety margin.
- **t3.micro (1 GB):** works only with the swap file below, and analyses run slower while
  swapping.

## Pick the instance

MediaPipe only runs on **x86-64**, so ARM types (t4g, Graviton) won't work.

| Account created | Free option | Notes |
|---|---|---|
| On or after 15 July 2025 | The free plan covers t3.micro, t3.small, c7i-flex.large and m7i-flex.large for 6 months, paid from the free credits ([AWS](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-free-tier-usage.html)) | **t3.small** (2 vCPU, 2 GB) is the sweet spot: about $15 a month of credits, so it lasts the full 6 months |
| Before 15 July 2025 | 750 hours a month of t3.micro for 12 months | 1 GB of memory: works with the swap file below, one analysis at a time |

Burstable instances (t3) run at full speed in bursts and then slow down. That's fine for
light use, but expect analyses to queue up if many people upload at once.

## 1. Launch the instance

In the EC2 console:

- **Image:** Ubuntu Server 24.04 LTS, **64-bit (x86)**.
- **Instance type:** t3.small (or t3.micro).
- **Key pair:** create one and download the `.pem` file.
- **Storage:** 30 GB gp3 (the free amount).
- **Security group:**
  - allow SSH (22) from **My IP** only;
  - allow HTTP (80) and HTTPS (443) from anywhere.

Then go to **Elastic IPs**, allocate one, and associate it with the instance. It's free while
attached, and it keeps the address fixed across restarts.

## 2. A free hostname for HTTPS

Browsers need HTTPS for the sign-in cookie, and HTTPS needs a hostname. Without buying a
domain:

1. Sign in at https://www.duckdns.org and create a subdomain, e.g. `serveanalyzer`.
2. Set its IP to the Elastic IP and click **update ip**.

Your site will be `https://serveanalyzer.duckdns.org`. Caddy gets the certificate on first
start. When you buy a domain later, point it at the same IP and change `DOMAIN` and
`SERVE_API_APP_URL`.

## 3. Email without a domain (Brevo)

1. Create a free account at https://www.brevo.com.
2. Under **Senders**, add and verify the address emails should come from (your own address
   works).
3. Under **SMTP & API**, create an SMTP key. Note the SMTP login it shows (it looks like
   `xxxx@smtp-brevo.com`).

Emails sent from a free-mail address (like Gmail) through another service are more likely to
land in spam. Check your spam folder when testing, and switch to your own domain (with Resend
or Brevo's domain verification) when you buy one.

## 4. Set up the server

```bash
ssh -i your-key.pem ubuntu@<elastic-ip>

# Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu && newgrp docker

# A 2 GB swap file, a safety margin for memory peaks (essential on t3.micro).
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

git clone https://github.com/AryanB-07/Serve-Analyzer.git
cd Serve-Analyzer
cp deploy/.env.example deploy/.env
nano deploy/.env
```

Fill in `deploy/.env`:

```bash
DOMAIN=serveanalyzer.duckdns.org
SERVE_API_APP_URL=https://serveanalyzer.duckdns.org
SERVE_API_SECRET=<python3 -c "import secrets; print(secrets.token_urlsafe(48))">

# The bundled Postgres and local disk storage: no RDS or S3 needed.
POSTGRES_PASSWORD=<a long random password>
SERVE_API_DATABASE_URL=postgresql://serve:<the same password>@postgres:5432/serve_analyzer
SERVE_API_STORAGE=local

# Brevo
SERVE_API_SMTP_HOST=smtp-relay.brevo.com
SERVE_API_SMTP_PORT=587
SERVE_API_SMTP_USERNAME=<your Brevo SMTP login>
SERVE_API_SMTP_PASSWORD=<your Brevo SMTP key>
SERVE_API_EMAIL_FROM=<the verified sender address>

# Small server: one API process, one analysis at a time.
API_PROCESSES=1
WORKERS=1
```

Delete the `AWS_*` and `SERVE_API_S3_*` lines; they're only for S3.

## 5. Start it

```bash
docker compose -f deploy/docker-compose.yml --profile bundled-db up -d --build
docker compose -f deploy/docker-compose.yml ps                  # api becomes "healthy"
curl https://serveanalyzer.duckdns.org/api/health               # {"status":"ok"}
python3 scripts/smoke_test.py https://serveanalyzer.duckdns.org # signs up, checks, deletes
```

The first build takes 5–10 minutes on a small instance. Then open the site, sign up, confirm the
email, and analyse a serve from your phone.

## 6. Monitoring and cost protection (free)

- **Uptime:** in UptimeRobot or Better Stack (both have free tiers), add two monitors:
  - `https://<host>/api/health` checks that the site and database are up;
  - `https://<host>/api/health/queue` returns 503 if an analysis has waited more than 10
    minutes, which means the worker has stopped.
- **Budget:** in AWS Billing, under **Budgets**, create a zero-spend budget. It emails you as
  soon as anything starts costing money.

## 7. Backups and the Privacy Policy

The bundled Postgres has no automatic backups. A nightly dump, kept for 7 days to match the
Privacy Policy's `backupRetentionDays`:

```bash
mkdir -p ~/backups
crontab -e
# add:
0 3 * * * cd ~/Serve-Analyzer && docker compose -f deploy/docker-compose.yml exec -T postgres pg_dump -U serve serve_analyzer | gzip > ~/backups/db-$(date +\%F).sql.gz && find ~/backups -name 'db-*.sql.gz' -mtime +7 -delete
```

Videos live on the instance's disk (the `objects` Docker volume), so take an EBS snapshot now
and then if you want them backed up too. Snapshots beyond the free allowance cost money.

## Updating

```bash
cd ~/Serve-Analyzer && git pull
docker compose -f deploy/docker-compose.yml --profile bundled-db up -d --build
```

Database migrations run automatically when the API starts.

## When to move up

- **Analyses queue for minutes:** move to a bigger instance (c7i-flex.large on the free plan),
  then raise `WORKERS`.
- **The disk fills:** move videos to S3 (`SERVE_API_STORAGE=s3`, see `docs/deployment.md`).
- **You need managed backups:** use RDS Postgres instead of the bundled one.

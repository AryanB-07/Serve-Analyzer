# Deploying on the AWS free tier

This guide runs the whole app on one small EC2 instance, with no domain and no email provider
to pay for. It takes about an hour the first time. `docs/deployment.md` covers the general
setup (managed Postgres, S3, more workers) once you outgrow this.

```
browser ──HTTPS──► EC2 instance (Docker): Caddy ─► API ─► Postgres (in a container)
                                                   └──► worker (MediaPipe) ─► videos on the disk
```

## What fits, measured

Peak memory of the production containers analysing a 1080p, 15-second serve on Linux, over
several analyses in a row:

| Process | Memory |
|---|---|
| Pose step: MediaPipe heavy model, in a short-lived child process that exits afterwards | about 545 MB |
| Worker, the rest of the time (analysis, drawing the overlay) | about 250 MB between jobs, up to 380 MB during one |
| ffmpeg, encoding the result videos to H.264 (while the pose step isn't running) | about 445 MB |
| API, one process (it never loads MediaPipe) | about 160 MB |
| Postgres | about 30–60 MB |
| Caddy (HTTPS and the website) | about 20 MB |

So an analysis peaks at about 0.9 GB for the worker, and about 1.1 GB with everything else.
The worker returns to about 250 MB between jobs and doesn't grow over time.

### Rehearsal: the worst clips allowed, on a 1 GB and a 2 GB server

`scripts/memory_rehearsal.py` measures every container's peak memory (the kernel's cgroup
counter, so short-lived children like the pose process and ffmpeg count) while analysing:
- the largest clips the upload limits still allow: 15 s of 1080p at 120 fps, which is 1,800
  frames, the maximum;
- 15 s of 10-bit 4K HEVC, an iPhone-style file that gets scaled down first;
- an ordinary 15 s 1080p clip.

`deploy/docker-compose.memory.yml` caps each container at its share of the server. Ubuntu and
Docker take about 250 MB, and the worker gets the rest, plus the 2 GB swap file the setup
script makes. These numbers are from Docker Desktop on a Mac emulating x86, so the times are
slower than a real t3 and only the comparisons between rows matter.

| Server | Clip | Result | Time | Worker peak | All containers |
|---|---|---|---|---|---|
| No caps | 1080p, 25 fps | succeeded | 63 s | 722 MB | 1,058 MB |
| No caps | 1080p, 120 fps (the maximum) | succeeded | 265 s | 757 MB | 1,097 MB |
| No caps | 4K HEVC, before one-thread decoding | succeeded | 69 s | **1,323 MB** | 1,663 MB |
| No caps | 4K HEVC, one-thread decoding (now) | succeeded | 69 s | 734 MB | 974 MB |
| **t3.small** (worker 1,450 MB + swap) | 1080p, 25 fps | succeeded | 63 s | 727 MB | 969 MB |
| **t3.small** | 1080p, 120 fps | succeeded | 297 s | 715 MB | 957 MB |
| **t3.small** | 4K HEVC | succeeded | 69 s | 741 MB | 999 MB |
| **t3.micro** (worker 450 MB + swap) | 1080p, 25 fps | succeeded | 78 s | 450 MB, the rest swapped | 677 MB |
| **t3.micro** | 1080p, 120 fps | succeeded | 304 s | 450 MB, the rest swapped | 680 MB |
| **t3.micro** | 4K HEVC | succeeded | 81 s | 450 MB, the rest swapped | 682 MB |

Two things came out of it:

- **4K needed fixing:** ffmpeg decoded it on every core, each thread holding full-size frames.
  The conversion now decodes with one thread, which halved the worker's peak at the same
  speed.
- **Every worst case fits both servers:**
  - **t3.small (2 GB):** fits comfortably. The worker never comes near its share, and about
    700 MB is left over. **Recommended.**
  - **t3.micro (1 GB):** every analysis still finishes, but the worker runs with half its
    memory in swap, which made analyses 15–25% slower here. EBS-backed swap on a real t3.micro
    is slower than a Mac's SSD, so expect more. Fine for trying it out; move to a t3.small
    before sharing the link widely.

Reproduce it with the smoke stack running (`KEEP=1 E2E=0 scripts/smoke_docker.sh`):

```bash
REHEARSAL_WORKER_MEM=450m REHEARSAL_WORKER_SWAP=2450m docker compose -p serve-smoke \
  --env-file deploy/smoke.env -f deploy/docker-compose.yml -f deploy/docker-compose.smoke.yml \
  -f deploy/docker-compose.memory.yml --profile bundled-db up -d --wait
python3 scripts/memory_rehearsal.py https://localhost:8443 --mailpit http://localhost:8025 your-clips.mp4
```

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

One command does steps 4, 5 and 7: it installs Docker, adds the swap file, downloads the code,
writes `deploy/.env` with generated secrets, schedules the nightly backup, starts everything,
and checks the site answers. It asks for the hostname and the three Brevo details.

```bash
ssh -i your-key.pem ubuntu@<elastic-ip>
curl -fsSL https://raw.githubusercontent.com/AryanB-07/Serve-Analyzer/main/scripts/server_setup.sh | bash
```

Optional: add `DUCKDNS_TOKEN=<your token>` before `bash` to keep the DuckDNS name pointed at
the server. It's safe to run again; it keeps an existing `deploy/.env`. Read the script first
if you like (`scripts/server_setup.sh`); the rest of this section is what it does, by hand.

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

The bundled Postgres has no automatic backups. `scripts/backup_db.sh` writes a nightly dump
to `~/backups`, kept for 7 days to match the Privacy Policy's `backupRetentionDays`, and refuses
to keep an incomplete one. The setup script schedules it; by hand:

```bash
crontab -e
# add:
0 3 * * * $HOME/Serve-Analyzer/scripts/backup_db.sh >> $HOME/backups.log 2>&1
```

To restore one (it stops the API and workers while it loads):

```bash
scripts/restore_db.sh ~/backups/db-2026-10-14.sql.gz
```

`scripts/test_backup_restore.sh` proves the pair works, and runs on every push as part of the
smoke test: it backs up, wipes the database, restores, and checks an account came back.

Videos live on the instance's disk (the `objects` Docker volume), so take an EBS snapshot now
and then if you want them backed up too. Snapshots beyond the free allowance cost money.

## Updating

```bash
cd ~/Serve-Analyzer && git pull
docker compose -f deploy/docker-compose.yml --profile bundled-db up -d --build
```

Database migrations run automatically when the API starts.

To see what people reported with "this result looks wrong":

```bash
docker compose -f deploy/docker-compose.yml exec api python -m serve_api.reports --days 14
```

## When to move up

- **Analyses queue for minutes:** move to a bigger instance (c7i-flex.large on the free plan),
  then raise `WORKERS`.
- **The disk fills:** move videos to S3 (`SERVE_API_STORAGE=s3`, see `docs/deployment.md`).
- **You need managed backups:** use RDS Postgres instead of the bundled one.

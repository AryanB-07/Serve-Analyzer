#!/usr/bin/env bash
# Set up Serve Analyzer on a fresh Ubuntu 24.04 server (an AWS EC2 t3.small or t3.micro) in one go:
# Docker, a swap file, the code, a deploy/.env with generated secrets, the nightly database
# backup, and the running stack. Safe to run again: it keeps an existing deploy/.env and swap.
#
# On the server (after `ssh -i key.pem ubuntu@<elastic-ip>`):
#
#   curl -fsSL https://raw.githubusercontent.com/AryanB-07/Serve-Analyzer/main/scripts/server_setup.sh | bash
#
# It asks for what it needs. Or pass the answers in, for example:
#
#   curl -fsSL …/server_setup.sh | DOMAIN=serveanalyzer.duckdns.org \
#     SMTP_LOGIN=xxxx@smtp-brevo.com SMTP_KEY=xsmtpsib-… EMAIL_FROM=you@example.com bash
#
# Optional: DUCKDNS_TOKEN keeps the DuckDNS name pointed at this server (every 5 minutes);
# REPO_URL / BRANCH / APP_DIR to change where the code comes from or goes; SKIP_START=1 to
# prepare everything without starting; WORKERS (default 1).
# See docs/deploy-aws-free-tier.md for the steps this replaces and what to do around them.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/AryanB-07/Serve-Analyzer.git}"
BRANCH="${BRANCH:-main}"
APP_DIR="${APP_DIR:-$HOME/Serve-Analyzer}"
SWAP_SIZE="${SWAP_SIZE:-2G}"
COMPOSE_FILE_ARGS=(-f deploy/docker-compose.yml --profile bundled-db)

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }
sudo_() { if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi; }

# Ask on the terminal when a value wasn't passed in (stdin is the script itself under curl | bash).
ask() {
  local var="$1" prompt="$2" secret="${3:-}" value="${!1:-}"
  if [ -z "$value" ]; then
    # Opening it is the real test: /dev/tty can exist without a terminal behind it (cloud-init).
    (exec < /dev/tty) 2>/dev/null || die "$var is not set and there's no terminal to ask on"
    if [ -n "$secret" ]; then read -r -s -p "$prompt: " value < /dev/tty; echo > /dev/tty
    else read -r -p "$prompt: " value < /dev/tty; fi
  fi
  [ -n "$value" ] || die "$var can't be empty"
  printf -v "$var" '%s' "$value"
}

# Replace this user's cron job matching $1 with the line $2. A new server has no crontab yet
# (`crontab -l` fails), which must not stop the script.
set_cron() {
  { crontab -l 2>/dev/null || true; } | { grep -v -- "$1" || true; } > /tmp/crontab.$$
  echo "$2" >> /tmp/crontab.$$
  crontab /tmp/crontab.$$
  rm -f /tmp/crontab.$$
}

random_secret() { head -c 48 /dev/urandom | base64 | tr -d '/+=\n' | head -c "${1:-48}"; }

# --- checks -----------------------------------------------------------------------------------
[ "$(uname -m)" = x86_64 ] || die "this needs an x86-64 server (MediaPipe has no ARM build); pick t3, not t4g"
# shellcheck source=/dev/null
. /etc/os-release 2>/dev/null || true
[ "${ID:-}" = ubuntu ] || echo "warning: tested on Ubuntu 24.04; this is ${PRETTY_NAME:-unknown}"

# --- Docker -----------------------------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  say "Installing Docker"
  curl -fsSL https://get.docker.com | sudo_ sh
fi
# (A Docker without a "docker" group, such as the snap package, keeps needing sudo; that's fine.)
if [ "$(id -u)" -ne 0 ] && getent group docker >/dev/null && ! id -nG | grep -qw docker; then
  sudo_ usermod -aG docker "$(id -un)"
fi
# This session isn't in the docker group yet; run docker through sudo until the next login.
docker_() { if docker info >/dev/null 2>&1; then docker "$@"; else sudo_ docker "$@"; fi; }

# --- swap -------------------------------------------------------------------------------------
if [ -n "${SKIP_SWAP:-}" ]; then :
elif swapon --show --noheadings | grep -q .; then
  echo "swap already on: $(swapon --show --noheadings | awk '{print $1, $3}')"
else
  say "Adding a $SWAP_SIZE swap file (a safety margin for memory peaks during an analysis)"
  sudo_ fallocate -l "$SWAP_SIZE" /swapfile
  sudo_ chmod 600 /swapfile
  sudo_ mkswap /swapfile >/dev/null
  sudo_ swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo_ tee -a /etc/fstab >/dev/null
fi

# --- code -------------------------------------------------------------------------------------
command -v git >/dev/null 2>&1 || { sudo_ apt-get update -qq && sudo_ apt-get install -y -qq git; }
if [ -d "$APP_DIR/.git" ]; then
  say "Updating $APP_DIR"
  git -C "$APP_DIR" pull --ff-only
else
  say "Downloading the code to $APP_DIR"
  git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

# --- configuration ----------------------------------------------------------------------------
if [ -f deploy/.env ]; then
  say "Keeping the existing deploy/.env"
else
  say "Writing deploy/.env"
  ask DOMAIN "Hostname (e.g. serveanalyzer.duckdns.org)"
  DOMAIN="${DOMAIN#https://}"; DOMAIN="${DOMAIN%%/*}"
  ask SMTP_LOGIN "Brevo SMTP login (looks like xxxx@smtp-brevo.com)"
  ask SMTP_KEY "Brevo SMTP key" secret
  ask EMAIL_FROM "Send emails from (the sender you verified in Brevo)"
  db_password="$(random_secret 32)"
  umask 077
  cat > deploy/.env <<ENV
# Written by scripts/server_setup.sh on $(date -u +%F). Never commit this file.
DOMAIN=$DOMAIN
SERVE_API_APP_URL=https://$DOMAIN
SERVE_API_ENV=production
SERVE_API_SECRET=$(random_secret 48)

# The bundled Postgres and local disk storage: no RDS or S3 needed.
POSTGRES_PASSWORD=$db_password
SERVE_API_DATABASE_URL=postgresql://serve:$db_password@postgres:5432/serve_analyzer
SERVE_API_STORAGE=local

# Email through Brevo's free plan.
SERVE_API_SMTP_HOST=${SMTP_HOST:-smtp-relay.brevo.com}
SERVE_API_SMTP_PORT=${SMTP_PORT:-587}
SERVE_API_SMTP_USERNAME=$SMTP_LOGIN
SERVE_API_SMTP_PASSWORD=$SMTP_KEY
SERVE_API_EMAIL_FROM=$EMAIL_FROM

# A small server: one API process, one analysis at a time.
API_PROCESSES=1
WORKERS=${WORKERS:-1}
ENV
  chmod 600 deploy/.env
  echo "secrets generated; deploy/.env is readable by $(id -un) only"
fi

# --- DuckDNS (optional) -----------------------------------------------------------------------
if [ -n "${DUCKDNS_TOKEN:-}" ]; then
  name="$(sed -n 's/^DOMAIN=\(.*\)\.duckdns\.org$/\1/p' deploy/.env)"
  [ -n "$name" ] || die "DUCKDNS_TOKEN given, but DOMAIN in deploy/.env isn't a duckdns.org name"
  say "Keeping $name.duckdns.org pointed at this server"
  printf 'url="https://www.duckdns.org/update?domains=%s&token=%s&ip="\n' "$name" "$DUCKDNS_TOKEN" > "$HOME/.duckdns"
  chmod 600 "$HOME/.duckdns"
  curl -fsS -K "$HOME/.duckdns" && echo
  set_cron '\.duckdns' "*/5 * * * * curl -fsS -K $HOME/.duckdns >/dev/null 2>&1"
fi

# --- nightly backup ---------------------------------------------------------------------------
say "Scheduling the nightly database backup (03:00, kept 7 days in ~/backups)"
set_cron 'scripts/backup_db.sh' "0 3 * * * $APP_DIR/scripts/backup_db.sh >> $HOME/backups.log 2>&1"

# --- start ------------------------------------------------------------------------------------
if [ -n "${SKIP_START:-}" ]; then
  say "Ready (SKIP_START set, so not started). Start with:"
  echo "  cd $APP_DIR && docker compose ${COMPOSE_FILE_ARGS[*]} up -d --build"
  exit 0
fi
say "Building and starting (5-10 minutes the first time)"
docker_ compose "${COMPOSE_FILE_ARGS[@]}" up -d --build --wait --wait-timeout 900
domain="$(sed -n 's/^DOMAIN=//p' deploy/.env)"

say "Checking https://$domain"
ok=""
for _ in $(seq 30); do
  if curl -fsS "https://$domain/api/health" >/dev/null 2>&1; then ok=1; break; fi
  sleep 10
done
if [ -n "$ok" ]; then
  echo "the site is up: https://$domain"
else
  echo "the containers are running, but https://$domain/api/health didn't answer yet."
  echo "Check the hostname points at this server's IP, and that ports 80 and 443 are open in the"
  echo "security group; Caddy keeps retrying the certificate. Logs: docker compose ${COMPOSE_FILE_ARGS[*]} logs web"
fi

cat <<NEXT

Next:
  - Run the smoke test:  python3 $APP_DIR/scripts/smoke_test.py https://$domain
  - Sign up on the site, confirm the email, and analyse a serve from your phone.
  - Add uptime monitors for https://$domain/api/health and /api/health/queue (UptimeRobot, free).
  - Log out and back in once, so your user can run docker without sudo.
Update later with: cd $APP_DIR && git pull && docker compose ${COMPOSE_FILE_ARGS[*]} up -d --build
NEXT

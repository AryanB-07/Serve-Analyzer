#!/usr/bin/env bash
# Runs scripts/server_setup.sh in a fresh Ubuntu 24.04 (x86-64) container, as the default
# "ubuntu" user with sudo like on EC2, and checks what it leaves behind: deploy/.env with
# generated secrets readable only by its owner, the backup cron job, and that a second run keeps
# everything. Docker is a stub here (the real stack is tested by smoke_docker.sh), and nothing
# is started (SKIP_START=1). The code is cloned from this checkout's committed HEAD.
#
#   scripts/test_server_setup.sh
set -euo pipefail
cd "$(dirname "$0")/.."

docker run --rm --platform linux/amd64 -v "$PWD:/src:ro" ubuntu:24.04 bash -c '
set -euo pipefail
apt-get update -qq >/dev/null && apt-get install -y -qq git curl cron sudo >/dev/null
id ubuntu >/dev/null 2>&1 || useradd -m ubuntu
echo "ubuntu ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ubuntu
printf "#!/bin/sh\necho \"docker stub: \$*\"\n" > /usr/local/bin/docker && chmod +x /usr/local/bin/docker
git config --global --add safe.directory "*"; sudo -u ubuntu -H git config --global --add safe.directory "*"
cp /src/scripts/server_setup.sh /tmp/setup.sh
run() { sudo -u ubuntu -H env REPO_URL=/src BRANCH="$(git -C /src rev-parse --abbrev-ref HEAD)" SKIP_SWAP=1 SKIP_START=1 "$@" bash /tmp/setup.sh; }
check() { if eval "$2"; then echo "  ok: $1"; else echo "FAIL: $1" >&2; exit 1; fi; }
env_file=/home/ubuntu/Serve-Analyzer/deploy/.env

echo "- missing answers and no terminal: refused with a clear message"
if out=$(run DOMAIN=x.duckdns.org 2>&1 </dev/null); then echo "FAIL: should have stopped"; exit 1; fi
echo "$out" | grep -q "SMTP_LOGIN is not set" && echo "  ok: says which value is missing"
rm -rf /home/ubuntu/Serve-Analyzer

echo "- first run"
run DOMAIN=https://serveanalyzer.duckdns.org/ SMTP_LOGIN=abc@smtp-brevo.com SMTP_KEY=xsmtpsib-key EMAIL_FROM=me@example.com > /tmp/first.log 2>&1 || { cat /tmp/first.log; exit 1; }
check "deploy/.env written" "[ -f $env_file ]"
check "only its owner can read it" "[ \"\$(stat -c %a:%U $env_file)\" = 600:ubuntu ]"
check "hostname cleaned up" "grep -qx DOMAIN=serveanalyzer.duckdns.org $env_file"
check "app URL is https" "grep -qx SERVE_API_APP_URL=https://serveanalyzer.duckdns.org $env_file"
check "production mode" "grep -qx SERVE_API_ENV=production $env_file"
check "Brevo settings" "grep -qx SERVE_API_SMTP_HOST=smtp-relay.brevo.com $env_file && grep -qx SERVE_API_SMTP_USERNAME=abc@smtp-brevo.com $env_file && grep -qx SERVE_API_SMTP_PASSWORD=xsmtpsib-key $env_file && grep -qx SERVE_API_EMAIL_FROM=me@example.com $env_file"
secret=$(sed -n "s/^SERVE_API_SECRET=//p" $env_file); pw=$(sed -n "s/^POSTGRES_PASSWORD=//p" $env_file)
check "a 48-character secret" "[ \${#secret} -eq 48 ]"
check "a 32-character database password" "[ \${#pw} -eq 32 ]"
check "the database URL uses that password" "grep -qx \"SERVE_API_DATABASE_URL=postgresql://serve:\$pw@postgres:5432/serve_analyzer\" $env_file"
check "nightly backup scheduled" "sudo -u ubuntu crontab -l | grep -qx \"0 3 \* \* \* /home/ubuntu/Serve-Analyzer/scripts/backup_db.sh >> /home/ubuntu/backups.log 2>&1\""
check "says how to start it" "grep -q \"docker compose -f deploy/docker-compose.yml --profile bundled-db up -d --build\" /tmp/first.log"

echo "- second run: keeps the configuration and adds no duplicate cron job"
before=$(sha256sum $env_file)
run > /tmp/second.log 2>&1 </dev/null || { cat /tmp/second.log; exit 1; }
check "deploy/.env unchanged" "[ \"\$(sha256sum $env_file)\" = \"\$before\" ]"
check "one backup job" "[ \"\$(sudo -u ubuntu crontab -l | grep -c backup_db.sh)\" -eq 1 ]"

echo "- a DuckDNS token with a non-DuckDNS hostname is refused"
sed -i "s/^DOMAIN=.*/DOMAIN=serve.example.com/" $env_file
if run DUCKDNS_TOKEN=t >/tmp/third.log 2>&1 </dev/null; then echo "FAIL: should have stopped"; exit 1; fi
grep -q "isn.t a duckdns.org name" /tmp/third.log && echo "  ok: explains why"
echo "OK: server setup script"
'

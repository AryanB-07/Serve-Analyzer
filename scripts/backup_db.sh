#!/usr/bin/env bash
# Dump the bundled Postgres to a dated, gzipped file and delete dumps older than the Privacy
# Policy's backup retention (7 days). The server setup script runs this nightly from cron.
#
#   scripts/backup_db.sh                    # writes ~/backups/db-YYYY-MM-DD.sql.gz
#   BACKUP_DIR=/mnt/backups KEEP_DAYS=7 scripts/backup_db.sh
#
# Restore one with scripts/restore_db.sh.
set -euo pipefail
cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
KEEP_DAYS="${KEEP_DAYS:-7}"
# COMPOSE_ARGS overrides the compose files and profile (the smoke test points it at its own stack).
read -r -a compose_args <<< "${COMPOSE_ARGS:--f deploy/docker-compose.yml --profile bundled-db}"
COMPOSE=(docker compose "${compose_args[@]}")

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
out="$BACKUP_DIR/db-$(date +%F).sql.gz"
tmp="$out.part"
trap 'rm -f "$tmp"' EXIT  # a failed dump leaves nothing behind
# --clean --if-exists: the dump drops and recreates each table, so it restores over anything.
"${COMPOSE[@]}" exec -T postgres pg_dump -U serve --clean --if-exists serve_analyzer | gzip > "$tmp"
# An empty or truncated dump must never replace a good one.
if ! gzip -t "$tmp" || [ "$(gzip -dc "$tmp" | grep -c 'PostgreSQL database dump complete')" -ne 1 ]; then
  rm -f "$tmp"
  echo "backup failed: the dump is incomplete" >&2
  exit 1
fi
mv "$tmp" "$out"
chmod 600 "$out"
find "$BACKUP_DIR" -name 'db-*.sql.gz' -mtime +"$KEEP_DAYS" -delete
echo "backed up to $out ($(du -h "$out" | cut -f1))"

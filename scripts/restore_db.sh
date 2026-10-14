#!/usr/bin/env bash
# Restore the bundled Postgres from a dump made by scripts/backup_db.sh.
#
#   scripts/restore_db.sh ~/backups/db-2026-10-14.sql.gz
#
# The API and workers are stopped while it loads, so nothing writes half-way through, then
# started again. Everything written since that dump is lost; videos (on the disk) are not
# touched, so analyses deleted since then come back without their files.
set -euo pipefail
cd "$(dirname "$0")/.."

dump="${1:?usage: scripts/restore_db.sh <db-YYYY-MM-DD.sql.gz>}"
[ -f "$dump" ] || { echo "no such file: $dump" >&2; exit 1; }
gzip -t "$dump" || { echo "$dump is not a valid gzip file" >&2; exit 1; }
# COMPOSE_ARGS overrides the compose files and profile (the smoke test points it at its own stack).
read -r -a compose_args <<< "${COMPOSE_ARGS:--f deploy/docker-compose.yml --profile bundled-db}"
COMPOSE=(docker compose "${compose_args[@]}")

if [ -z "${YES:-}" ]; then
  read -r -p "Replace the current database with $dump? Type yes: " answer < /dev/tty
  [ "$answer" = yes ] || { echo "cancelled"; exit 1; }
fi

echo "- stopping the API and workers"
"${COMPOSE[@]}" stop api worker
echo "- loading $dump"
gzip -dc "$dump" | "${COMPOSE[@]}" exec -T postgres psql -U serve -d serve_analyzer -q -v ON_ERROR_STOP=1 >/dev/null
echo "- starting the API and workers"
"${COMPOSE[@]}" up -d --wait api worker
echo "restored from $dump"

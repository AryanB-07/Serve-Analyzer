#!/usr/bin/env bash
# Proves a backup restores: against a running stack (scripts/smoke_docker.sh runs this), make an
# account, back up, make a second account, wipe the database, restore, and check the first
# account is back and the second is gone.
#
#   COMPOSE_ARGS="-p serve-smoke --env-file deploy/smoke.env -f deploy/docker-compose.yml \
#     -f deploy/docker-compose.smoke.yml --profile bundled-db" scripts/test_backup_restore.sh https://localhost:8443
set -euo pipefail
cd "$(dirname "$0")/.."

base="${1:?usage: scripts/test_backup_restore.sh <base url>}"
read -r -a compose_args <<< "${COMPOSE_ARGS:--f deploy/docker-compose.yml --profile bundled-db}"
COMPOSE=(docker compose "${compose_args[@]}")
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
password="backup test password"

status() {  # status <method> <path> [json]: prints the HTTP status, keeping cookies per account
  curl -ks -o /dev/null -w '%{http_code}' -X "$1" "$base/api$2" -H 'Content-Type: application/json' \
    -b "$work/cookies" -c "$work/cookies" ${3:+--data "$3"}
}
account() { printf '{"email":"%s","password":"%s","accept_terms":true}' "$1" "$password"; }
login() { printf '{"email":"%s","password":"%s"}' "$1" "$password"; }
check() { if [ "$2" = "$3" ]; then echo "  ok: $1"; else echo "FAIL: $1 (got $2, expected $3)" >&2; exit 1; fi; }

kept="backup-kept-$RANDOM$RANDOM@example.com"
lost="backup-lost-$RANDOM$RANDOM@example.com"

echo "- an account that the backup will contain"
check "sign up $kept" "$(status POST /auth/signup "$(account "$kept")")" 201

echo "- back up"
BACKUP_DIR="$work/backups" COMPOSE_ARGS="${compose_args[*]}" scripts/backup_db.sh
dump="$(ls "$work"/backups/db-*.sql.gz)"

echo "- an account made after the backup"
rm -f "$work/cookies"
check "sign up $lost" "$(status POST /auth/signup "$(account "$lost")")" 201

echo "- lose the database"
"${COMPOSE[@]}" exec -T postgres psql -U serve -d serve_analyzer -q -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
rm -f "$work/cookies"
check "nobody can sign in" "$(status POST /auth/login "$(login "$kept")")" 500

echo "- restore"
YES=1 COMPOSE_ARGS="${compose_args[*]}" scripts/restore_db.sh "$dump"

echo "- check"
rm -f "$work/cookies"
check "$kept is back" "$(status POST /auth/login "$(login "$kept")")" 200
check "and is still signed in afterwards" "$(status GET /auth/me)" 200
check "its data is usable: delete it" "$(status DELETE /auth/me "{\"password\":\"$password\"}")" 204
rm -f "$work/cookies"
check "$lost (made after the backup) is gone" "$(status POST /auth/login "$(login "$lost")")" 401
echo "OK: the backup restored"

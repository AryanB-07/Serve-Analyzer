#!/usr/bin/env bash
# Build the production images, start them with test settings (bundled Postgres, a Mailpit
# inbox, self-signed HTTPS on :8443), run the end-to-end smoke test, and clean up.
#
#   scripts/smoke_docker.sh            # build, test, stop
#   KEEP=1 scripts/smoke_docker.sh     # leave the stack running afterwards (https://localhost:8443)
set -euo pipefail
cd "$(dirname "$0")/.."

compose() {
  docker compose -p serve-smoke --env-file deploy/smoke.env \
    -f deploy/docker-compose.yml -f deploy/docker-compose.smoke.yml --profile bundled-db "$@"
}

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then compose logs --no-color --tail 200 || true; fi
  if [ -z "${KEEP:-}" ]; then compose down -v --remove-orphans >/dev/null 2>&1 || true; fi
  exit "$status"
}
trap cleanup EXIT

compose build
compose up -d --wait --wait-timeout "${WAIT_TIMEOUT:-300}"
python3 scripts/smoke_test.py https://localhost:8443 --mailpit http://localhost:8025 --insecure \
  --timeout "${ANALYSIS_TIMEOUT:-600}"

#!/usr/bin/env bash
# Build the production images, start them with test settings (bundled Postgres, a Mailpit
# inbox, self-signed HTTPS on :8443), run the end-to-end smoke test, and clean up.
#
#   scripts/smoke_docker.sh            # build, test, stop
#   KEEP=1 scripts/smoke_docker.sh     # leave the stack running afterwards (https://localhost:8443)
#
# Then a backup is restored (scripts/test_backup_restore.sh; BACKUP_TEST=0 skips it), and the
# browser tests (frontend/e2e) run against the same stack, when Playwright is installed
# (cd frontend && npm ci && npx playwright install chromium). E2E=1 makes them required, E2E=0
# skips them.
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

if [ "${BACKUP_TEST:-1}" != 0 ]; then
  COMPOSE_ARGS="-p serve-smoke --env-file deploy/smoke.env -f deploy/docker-compose.yml -f deploy/docker-compose.smoke.yml --profile bundled-db" \
    scripts/test_backup_restore.sh https://localhost:8443
fi

if [ "${E2E:-}" != 0 ]; then
  if [ -x frontend/node_modules/.bin/playwright ]; then
    (cd frontend && E2E_BASE_URL=https://localhost:8443 MAILPIT_URL=http://localhost:8025 npx playwright test)
  elif [ "${E2E:-}" = 1 ]; then
    echo "E2E=1 but Playwright isn't installed (cd frontend && npm ci)" >&2
    exit 1
  else
    echo "Skipping the browser tests: Playwright isn't installed (cd frontend && npm ci)"
  fi
fi

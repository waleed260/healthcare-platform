#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVIDENCE_DIR="${ROOT_DIR}/docs/reports/evidence"
LOG_FILE="${EVIDENCE_DIR}/verify-all-${STAMP}.log"
mkdir -p "${EVIDENCE_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "verify-all started at ${STAMP}"
: "${DATABASE_MIGRATION_URL:?DATABASE_MIGRATION_URL must point to the migrator PostgreSQL role}"
: "${DATABASE_URL:?DATABASE_URL must point to the runtime PostgreSQL role}"
export SEED_DATABASE_URL="${SEED_DATABASE_URL:-${DATABASE_MIGRATION_URL}}"
export TEST_ADMIN_DATABASE_URL="${TEST_ADMIN_DATABASE_URL:-${DATABASE_MIGRATION_URL}}"
export TEST_DATABASE_URL="${TEST_DATABASE_URL:-${DATABASE_URL}}"
export APP_ENV="${APP_ENV:-test}"

if [[ "${APP_ENV}" != "test" && "${APP_ENV}" != "local" ]]; then
  echo "APP_ENV must be test or local for deterministic seed verification." >&2
  exit 1
fi
command -v psql >/dev/null 2>&1 || { echo "psql is required for PostgreSQL evidence." >&2; exit 1; }

run_phase() {
  local label="$1"
  shift
  echo
  echo "===== ${label} ====="
  "$@"
}

run_phase "migrations" bash -c "cd '${ROOT_DIR}/apps/api' && DATABASE_URL='${DATABASE_MIGRATION_URL}' .venv/bin/alembic upgrade head"
run_phase "seed pass 1" bash -c "cd '${ROOT_DIR}/apps/api' && SEED_DATABASE_URL='${SEED_DATABASE_URL}' APP_ENV='${APP_ENV}' PYTHONPATH=. .venv/bin/python scripts/seed_demo.py"
run_phase "seed pass 2" bash -c "cd '${ROOT_DIR}/apps/api' && SEED_DATABASE_URL='${SEED_DATABASE_URL}' APP_ENV='${APP_ENV}' PYTHONPATH=. .venv/bin/python scripts/seed_demo.py"

RUNTIME_PSQL_URL="${TEST_DATABASE_URL/postgresql+psycopg:/postgresql:}"
run_phase "runtime-role seed visibility" psql "${RUNTIME_PSQL_URL}" -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;
SELECT set_config('app.clinic_id', '07c5156f-411f-56e1-b46f-8e3875f44a86', true);
DO $$
BEGIN
  IF (SELECT count(*) FROM patients) <> 4 THEN RAISE EXCEPTION 'clinic A patient count mismatch'; END IF;
  IF (SELECT count(*) FROM appointments) <> 4 THEN RAISE EXCEPTION 'clinic A appointment count mismatch'; END IF;
  IF (SELECT count(*) FROM patients WHERE clinic_id = 'e007336b-b7e4-5579-a129-c65da62ec259') <> 0 THEN RAISE EXCEPTION 'clinic A context can see clinic B patients'; END IF;
END $$;
COMMIT;
SQL

run_phase "seed verifier" bash -c "cd '${ROOT_DIR}' && SEED_DATABASE_URL='${SEED_DATABASE_URL}' TEST_DATABASE_URL='${TEST_DATABASE_URL}' PYTHONPATH=. apps/api/.venv/bin/python infra/verify_seed.py"
run_phase "API tests" bash -c "cd '${ROOT_DIR}/apps/api' && DATABASE_URL='${DATABASE_URL}' TEST_ADMIN_DATABASE_URL='${TEST_ADMIN_DATABASE_URL}' TEST_DATABASE_URL='${TEST_DATABASE_URL}' PYTHONPATH=. .venv/bin/python -m pytest -q"
run_phase "web lint (zero warnings)" bash -c "cd '${ROOT_DIR}/apps/web' && npx eslint . --max-warnings=0"
run_phase "web TypeScript" bash -c "cd '${ROOT_DIR}/apps/web' && npx tsc --noEmit -p tsconfig.json"
run_phase "web production build" bash -c "cd '${ROOT_DIR}/apps/web' && npm run build"

mapfile -t SPECS < <(cd "${ROOT_DIR}/apps/web" && find tests -maxdepth 1 -name '*.spec.ts' -print | shuf)
echo
echo "===== shuffled Playwright specs ====="
printf 'spec: %s\n' "${SPECS[@]}"
(cd "${ROOT_DIR}/apps/web" && npm run test:e2e -- "${SPECS[@]}")

NEGATIVE_LOG="${EVIDENCE_DIR}/tenant-negative-${STAMP}.log"
echo
echo "===== tenant negative control (expected failure) ====="
set +e
(cd "${ROOT_DIR}/apps/web" && BREAK_TENANT_ISOLATION=1 npm run test:e2e -- tenant-isolation.spec.ts --project=chromium) 2>&1 | tee "${NEGATIVE_LOG}"
NEGATIVE_STATUS="${PIPESTATUS[0]}"
set -e
if [[ "${NEGATIVE_STATUS}" -eq 0 ]]; then echo "Negative control unexpectedly passed." >&2; exit 1; fi
if ! grep -q "Synthetic Patient B" "${NEGATIVE_LOG}"; then echo "Negative control failed before the tenant assertion; inspect ${NEGATIVE_LOG}." >&2; exit 1; fi
echo "Negative control failed on the injected tenant data as required."

if command -v lighthouse >/dev/null 2>&1; then
  LIGHTHOUSE_OUTPUT="${EVIDENCE_DIR}/lighthouse-mobile-${STAMP}.json"
  echo
  echo "===== Lighthouse mobile ====="
  (cd "${ROOT_DIR}/apps/web" && npm run start -- -H 127.0.0.1 -p 3000 >"${EVIDENCE_DIR}/next-${STAMP}.log" 2>&1 & echo $! >"${EVIDENCE_DIR}/next-${STAMP}.pid")
  NEXT_PID="$(cat "${EVIDENCE_DIR}/next-${STAMP}.pid")"
  trap 'kill "${NEXT_PID}" 2>/dev/null || true' EXIT
  for _ in $(seq 1 30); do if curl --fail --silent http://127.0.0.1:3000/ >/dev/null; then break; fi; sleep 1; done
  lighthouse http://127.0.0.1:3000/ --form-factor=mobile --only-categories=performance --output=json --output-path="${LIGHTHOUSE_OUTPUT}" --chrome-flags="--headless --no-sandbox"
else
  echo "Lighthouse not installed; performance evidence skipped by design."
fi

echo
echo "verify-all passed. Evidence log: ${LOG_FILE}"

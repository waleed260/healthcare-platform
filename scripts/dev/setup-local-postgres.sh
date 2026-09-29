#!/usr/bin/env bash
set -euo pipefail

# Gate 0 helper for a native Ubuntu PostgreSQL installation. Run this script
# on the host with sudo available; it is intentionally not run automatically
# by the application or test suite.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

DB_NAME="${DB_NAME:-healthcare}"
DB_PORT="${DB_PORT:-5432}"
MIGRATOR_ROLE="${MIGRATOR_ROLE:-healthcare_migrator}"
MIGRATOR_PASSWORD="${MIGRATOR_PASSWORD:-healthcare_migrator_dev}"
RUNTIME_ROLE="${RUNTIME_ROLE:-healthcare_runtime}"
RUNTIME_PASSWORD="${RUNTIME_PASSWORD:-healthcare_runtime_dev}"
PG_MAJOR="${PG_MAJOR:-16}"

if [[ "$(uname -s)" != "Linux" || ! -f /etc/os-release ]]; then
  echo "This helper supports Ubuntu/Debian hosts with apt and systemd." >&2
  exit 1
fi

# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != "ubuntu" && "${ID_LIKE:-}" != *debian* ]]; then
  echo "Unsupported distribution: ${ID:-unknown}. Install PostgreSQL ${PG_MAJOR} and contrib manually." >&2
  exit 1
fi

if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo is required to install and configure PostgreSQL." >&2
  exit 1
fi

sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

if ! apt-cache show "postgresql-${PG_MAJOR}" >/dev/null 2>&1; then
  # PostgreSQL 16 is supplied by the PostgreSQL Apt Repository on older Ubuntu
  # releases. The key is installed as a scoped keyring, never trusted globally.
  sudo install -d -m 0755 /etc/apt/keyrings
  curl --fail --silent --show-error https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    | gpg --dearmor \
    | sudo tee /etc/apt/keyrings/postgresql.gpg >/dev/null
  echo "deb [signed-by=/etc/apt/keyrings/postgresql.gpg] http://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
    | sudo tee /etc/apt/sources.list.d/pgdg.list >/dev/null
  sudo apt-get update
fi

sudo apt-get install -y "postgresql-${PG_MAJOR}" "postgresql-client-${PG_MAJOR}" "postgresql-contrib-${PG_MAJOR}"
sudo systemctl enable --now postgresql

if ! sudo -u postgres psql --no-psqlrc -Atqc "SELECT 1 FROM pg_roles WHERE rolname = '${MIGRATOR_ROLE}'" | grep -qx 1; then
  sudo -u postgres psql --no-psqlrc -v ON_ERROR_STOP=1 -c "CREATE ROLE \"${MIGRATOR_ROLE}\" LOGIN SUPERUSER CREATEDB CREATEROLE PASSWORD '${MIGRATOR_PASSWORD}';"
else
  sudo -u postgres psql --no-psqlrc -v ON_ERROR_STOP=1 -c "ALTER ROLE \"${MIGRATOR_ROLE}\" WITH LOGIN SUPERUSER CREATEDB CREATEROLE PASSWORD '${MIGRATOR_PASSWORD}';"
fi

if ! sudo -u postgres psql --no-psqlrc -Atqc "SELECT 1 FROM pg_roles WHERE rolname = '${RUNTIME_ROLE}'" | grep -qx 1; then
  sudo -u postgres psql --no-psqlrc -v ON_ERROR_STOP=1 -c "CREATE ROLE \"${RUNTIME_ROLE}\" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD '${RUNTIME_PASSWORD}';"
else
  sudo -u postgres psql --no-psqlrc -v ON_ERROR_STOP=1 -c "ALTER ROLE \"${RUNTIME_ROLE}\" WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD '${RUNTIME_PASSWORD}';"
fi

if ! sudo -u postgres psql --no-psqlrc -Atqc "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}'" | grep -qx 1; then
  sudo -u postgres createdb --owner="${MIGRATOR_ROLE}" --port="${DB_PORT}" "${DB_NAME}"
fi

sudo -u postgres psql --no-psqlrc -v ON_ERROR_STOP=1 --dbname="${DB_NAME}" --port="${DB_PORT}" <<SQL
ALTER DATABASE "${DB_NAME}" OWNER TO "${MIGRATOR_ROLE}";
GRANT CONNECT ON DATABASE "${DB_NAME}" TO "${RUNTIME_ROLE}";
GRANT USAGE ON SCHEMA public TO "${RUNTIME_ROLE}";
CREATE EXTENSION IF NOT EXISTS btree_gist;
SQL

umask 077
if [[ ! -f "${ENV_FILE}" ]]; then
  if [[ -f "${ROOT_DIR}/.env.example" ]]; then
    cp "${ROOT_DIR}/.env.example" "${ENV_FILE}"
  else
    : >"${ENV_FILE}"
  fi
fi

ENV_TMP="$(mktemp "${ENV_FILE}.tmp.XXXXXX")"
trap 'rm -f "${ENV_TMP:-}"' EXIT
awk \
  -v migration="DATABASE_MIGRATION_URL=postgresql+psycopg://${MIGRATOR_ROLE}:${MIGRATOR_PASSWORD}@localhost:${DB_PORT}/${DB_NAME}" \
  -v runtime="DATABASE_URL=postgresql+psycopg://${RUNTIME_ROLE}:${RUNTIME_PASSWORD}@localhost:${DB_PORT}/${DB_NAME}" \
  -v seed="SEED_DATABASE_URL=postgresql+psycopg://${MIGRATOR_ROLE}:${MIGRATOR_PASSWORD}@localhost:${DB_PORT}/${DB_NAME}" \
  -v admin="TEST_ADMIN_DATABASE_URL=postgresql+psycopg://${MIGRATOR_ROLE}:${MIGRATOR_PASSWORD}@localhost:${DB_PORT}/${DB_NAME}" \
  -v test="TEST_DATABASE_URL=postgresql+psycopg://${RUNTIME_ROLE}:${RUNTIME_PASSWORD}@localhost:${DB_PORT}/${DB_NAME}" '
  BEGIN { lines["DATABASE_MIGRATION_URL"] = migration; lines["DATABASE_URL"] = runtime; lines["SEED_DATABASE_URL"] = seed; lines["TEST_ADMIN_DATABASE_URL"] = admin; lines["TEST_DATABASE_URL"] = test }
  {
    split($0, parts, "="); key = parts[1]
    if (key in lines) { if (!seen[key]++) print lines[key]; next }
    print
  }
  END { for (key in lines) if (!seen[key]) print lines[key] }
' "${ENV_FILE}" >"${ENV_TMP}"
chmod 600 "${ENV_TMP}"
mv "${ENV_TMP}" "${ENV_FILE}"
trap - EXIT

echo "PostgreSQL ${PG_MAJOR} is ready: ${DB_NAME} on localhost:${DB_PORT}."
echo "Connection strings written to ${ENV_FILE} (passwords omitted from output)."

#!/bin/sh
# Optionally apply migrations before serving (set RUN_MIGRATIONS_ON_START=true).
# Migrations use DATABASE_MIGRATION_URL (owner role); the app itself runs as
# DATABASE_URL (healthcare_runtime). Never point DATABASE_URL at the owner.
set -eu
if [ "${RUN_MIGRATIONS_ON_START:-false}" = "true" ]; then
  echo "[entrypoint] applying migrations"
  alembic upgrade head
fi
exec "$@"

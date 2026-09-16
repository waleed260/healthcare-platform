#!/usr/bin/env bash
set -euo pipefail

: "${BACKUP_FILE:?BACKUP_FILE must point to a verified custom-format dump}"
: "${RESTORE_DATABASE_URL:?RESTORE_DATABASE_URL must target an isolated restore database}"

if [[ "${CONFIRM_RESTORE:-}" != "YES" ]]; then
  echo "Refusing restore: set CONFIRM_RESTORE=YES for an isolated restore target." >&2
  exit 2
fi

sha256sum --check "$BACKUP_FILE.sha256"
pg_restore --clean --if-exists --no-owner --no-privileges --dbname="$RESTORE_DATABASE_URL" "$BACKUP_FILE"
psql "$RESTORE_DATABASE_URL" -v ON_ERROR_STOP=1 -c "SELECT count(*) > 0 AS migrations_present FROM alembic_version;"
psql "$RESTORE_DATABASE_URL" -v ON_ERROR_STOP=1 -c "SELECT count(*) AS forced_rls_tables FROM pg_class WHERE relrowsecurity AND relforcerowsecurity;"
echo "Restore verification completed against the isolated target."

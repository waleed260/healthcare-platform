#!/usr/bin/env bash
set -euo pipefail

: "${BACKUP_FILE:?BACKUP_FILE must point to a verified custom-format dump}"
: "${RESTORE_DATABASE_URL:?RESTORE_DATABASE_URL must target an isolated restore database}"

if [[ "${CONFIRM_RESTORE:-}" != "YES" ]]; then
  echo "Refusing restore: set CONFIRM_RESTORE=YES for an isolated restore target." >&2
  exit 2
fi
if [[ "${ISOLATED_RESTORE:-}" != "YES" ]]; then
  echo "Refusing restore: set ISOLATED_RESTORE=YES only after provisioning a disposable isolated target." >&2
  exit 2
fi
if [[ -n "${DATABASE_URL:-}" && "$RESTORE_DATABASE_URL" == "$DATABASE_URL" ]]; then
  echo "Refusing restore: restore target must not equal DATABASE_URL." >&2
  exit 2
fi
if [[ ! -f "$BACKUP_FILE" || ! -f "$BACKUP_FILE.sha256" ]]; then
  echo "Refusing restore: dump and checksum files must both exist." >&2
  exit 2
fi

sha256sum --check "$BACKUP_FILE.sha256"
pg_restore --list "$BACKUP_FILE" >/dev/null
pg_restore --clean --if-exists --no-owner --no-privileges --dbname="$RESTORE_DATABASE_URL" "$BACKUP_FILE"
psql "$RESTORE_DATABASE_URL" -v ON_ERROR_STOP=1 <<'SQL'
DO $$
DECLARE
  required_tables text[] := ARRAY[
    'patients', 'appointments', 'patient_notes', 'patient_documents',
    'follow_up_tasks', 'queue_entries', 'notifications', 'websites',
    'website_versions', 'website_pages', 'website_sections'
  ];
  forced_count integer;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM alembic_version) THEN
    RAISE EXCEPTION 'restore verification failed: alembic_version is empty';
  END IF;

  SELECT count(*) INTO forced_count
  FROM pg_class
  WHERE relname = ANY(required_tables)
    AND relnamespace = 'public'::regnamespace
    AND relrowsecurity
    AND relforcerowsecurity;
  IF forced_count <> cardinality(required_tables) THEN
    RAISE EXCEPTION 'restore verification failed: expected % forced-RLS tables, found %', cardinality(required_tables), forced_count;
  END IF;
  RAISE NOTICE 'restore verification passed: migration and forced-RLS checks';
END;
$$;
SQL
echo "Restore verification completed against the isolated target."

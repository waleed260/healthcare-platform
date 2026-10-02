#!/bin/sh
# Runs once when the database volume is first created, BEFORE migrations (they GRANT to this role).
# The password comes from HEALTHCARE_RUNTIME_PASSWORD (docker.env) and defaults to a dev value.
set -eu
psql -v ON_ERROR_STOP=1 -v pw="${HEALTHCARE_RUNTIME_PASSWORD:-healthcare_runtime_dev}" --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
SELECT format('CREATE ROLE healthcare_runtime LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT', :'pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'healthcare_runtime') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO healthcare_runtime', current_database()) \gexec
SQL

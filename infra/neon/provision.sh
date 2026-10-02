#!/usr/bin/env bash
# Provision a Neon (or any Postgres 16) database: runtime role -> migrations as owner -> verification.
#   OWNER_URL      libpq URL of the schema owner, DIRECT host   (postgresql://owner:pw@ep-xxx.neon.tech/db?sslmode=require)
#   RUNTIME_PASSWORD  password for healthcare_runtime (generate one; keep it only in docker.env or a password manager)
# Table privileges are granted by the migrations themselves, deliberately narrower than blanket GRANTs:
# do NOT add "GRANT ... ON ALL TABLES" for the runtime role.
set -euo pipefail
: "${OWNER_URL:?set OWNER_URL (direct owner connection)}" "${RUNTIME_PASSWORD:?set RUNTIME_PASSWORD}"
cd "$(dirname "$0")/../.."
psql "$OWNER_URL" -v ON_ERROR_STOP=1 -v runtime_password="$RUNTIME_PASSWORD" -f infra/neon/001_bootstrap_runtime_role.sql
SQLALCHEMY_URL="postgresql+psycopg://${OWNER_URL#*://}"
(cd apps/api && DATABASE_URL="$SQLALCHEMY_URL" DATABASE_MIGRATION_URL="$SQLALCHEMY_URL" alembic upgrade head)
psql "$OWNER_URL" -v ON_ERROR_STOP=1 -Atc "SELECT 'alembic head: ' || version_num FROM alembic_version"
psql "$OWNER_URL" -v ON_ERROR_STOP=1 -Atc "SELECT 'runtime role owns tables: ' || count(*) FROM pg_tables WHERE schemaname='public' AND tableowner='healthcare_runtime'"

# --- verify the runtime role really can use what the migrations created (silent-failure guard) ---
missing=$(psql "$OWNER_URL" -v ON_ERROR_STOP=1 -Atc "SELECT string_agg(c.relname, ', ' ORDER BY c.relname) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND c.relname <> 'alembic_version' AND NOT has_table_privilege('healthcare_runtime', c.oid, 'SELECT')")
if [ -n "$missing" ]; then echo "FAIL: healthcare_runtime has no SELECT on: $missing"; exit 1; fi
echo "runtime SELECT privilege: ok on every public table"
RUNTIME_URL=$(python3 - <<PY
import os, urllib.parse as u
parts = u.urlsplit(os.environ["OWNER_URL"])
host = parts.netloc.rsplit("@", 1)[-1]
print(u.urlunsplit((parts.scheme, "healthcare_runtime:" + u.quote(os.environ["RUNTIME_PASSWORD"], safe="") + "@" + host, parts.path, parts.query, "")))
PY
)
psql "$RUNTIME_URL" -v ON_ERROR_STOP=1 -Atc "SELECT 'runtime read plans: ' || count(*) FROM plans"
psql "$RUNTIME_URL" -v ON_ERROR_STOP=1 -Atc "SELECT 'runtime can INSERT clinics: ' || has_table_privilege('healthcare_runtime','public.clinics','INSERT')"
echo "OK. Use the POOLED host + healthcare_runtime for DATABASE_URL and this OWNER_URL (direct) for DATABASE_MIGRATION_URL (optional external Postgres; the Docker stack ships its own database)."

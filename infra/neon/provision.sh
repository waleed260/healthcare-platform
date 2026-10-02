#!/usr/bin/env bash
# Provision a Neon (or any Postgres 16) database: runtime role -> migrations as owner -> verification.
#   OWNER_URL      libpq URL of the schema owner, DIRECT host   (postgresql://owner:pw@ep-xxx.neon.tech/db?sslmode=require)
#   RUNTIME_PASSWORD  password for healthcare_runtime (generate one; store it only in Render)
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
echo "OK. Use the POOLED host + healthcare_runtime for DATABASE_URL and this OWNER_URL (direct) for DATABASE_MIGRATION_URL."

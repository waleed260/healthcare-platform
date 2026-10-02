-- Run FIRST, as the Neon owner (DIRECT connection), BEFORE migrations: migrations GRANT to healthcare_runtime,
-- so the role must already exist. Usage: psql "$OWNER_URL" -v runtime_password="$PW" -f 001_bootstrap_runtime_role.sql
SELECT format('CREATE ROLE healthcare_runtime LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT', :'runtime_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'healthcare_runtime') \gexec
SELECT format('ALTER ROLE healthcare_runtime PASSWORD %L', :'runtime_password') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO healthcare_runtime', current_database()) \gexec
GRANT USAGE ON SCHEMA public TO healthcare_runtime;

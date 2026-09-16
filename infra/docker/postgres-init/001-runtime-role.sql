CREATE ROLE healthcare_runtime LOGIN PASSWORD 'healthcare_runtime_dev' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
GRANT CONNECT ON DATABASE healthcare TO healthcare_runtime;

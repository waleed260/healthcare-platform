# Database & Migration Audit

## Database Connection Resolution

### Runtime connection (`DATABASE_URL`)

**Source**: `app/core/config.py:14`
```python
database_url: str = "postgresql+psycopg://healthcare_runtime:healthcare_runtime_dev@localhost:5432/healthcare"
```

- Default points to `localhost` — a local dev database.
- `render.yaml:27-28` declares `DATABASE_URL` with `sync: false` — must be set manually in Render dashboard.
- If NOT set, the app will attempt to connect to `localhost:5432`, which doesn't exist on Render. **This will fail the health check and prevent the service from starting.** Render will not mark it healthy. **No silent wrong-database risk.**

### Migration connection (`DATABASE_MIGRATION_URL`)

**Source**: `app/core/config.py:15`
```python
database_migration_url: str = ""
```

**Source**: `migrations/env.py:11`
```python
migration_url = settings.database_migration_url or settings.database_url
```

- Falls back to `DATABASE_URL` if empty.
- `render.yaml:29-30` declares `DATABASE_MIGRATION_URL` with `sync: false`.
- **Risk**: If `DATABASE_MIGRATION_URL` is left empty, migrations run against the runtime connection. For Neon, this means the runtime role needs schema-alter privileges, which violates least-privilege. Migrations should use the owner/migrator role.
- **Recommendation**: Always set `DATABASE_MIGRATION_URL` to the Neon direct (non-pooled) connection with the migrator role.

### Connection pooling

**Source**: `app/db/session.py:14-22`

| Setting | Value | Source |
|---------|-------|--------|
| `pool_pre_ping` | `True` | Hardcoded |
| `pool_size` | `5` | render.yaml `DB_POOL_SIZE=5` |
| `max_overflow` | `10` | render.yaml `DB_MAX_OVERFLOW=10` |
| `pool_timeout` | `30` | Default in config.py:19 |
| `pool_recycle` | `300` | Default in config.py:20 |
| `connect_timeout` | `5` | Default in config.py:17 |
| `cursor_factory` | `psycopg.ClientCursor` | Hardcoded — compatible with PgBouncer/Neon pooler |

**Max connections per process**: `pool_size + max_overflow = 15`

With `WEB_CONCURRENCY=2`: 2 processes × 15 max = **30 connections**. Plus the worker thread in each process uses `SessionLocal()` which draws from the same pool.

With `WEB_CONCURRENCY=1`: 1 process × 15 max = **15 connections**. Neon Free allows 5 active connections by default but supports up to 10,000 via the pooler. **Must use Neon's pooled connection string.**

**Recommendation**: For `WEB_CONCURRENCY=1`, reduce `DB_POOL_SIZE=3` and `DB_MAX_OVERFLOW=5` to stay well within Neon's limits.

### Neon pooled vs direct connections

- **Pooled** (`-pooler` hostname): For `DATABASE_URL` (runtime). PgBouncer-based, handles connection multiplexing. Compatible because the app uses `ClientCursor` (no server-side prepared statements).
- **Direct** (standard hostname): For `DATABASE_MIGRATION_URL`. Alembic uses `NullPool` (`migrations/env.py:26`), so it creates and closes connections without pooling — direct connection is correct.

### SSL

Neon requires SSL. psycopg3 defaults to SSL when connecting to non-localhost hosts. The connection string from Neon includes `sslmode=require`. **No additional SSL configuration needed.**

## Migration Execution

### Startup behavior

`docker-entrypoint.sh` runs `alembic upgrade head` when `RUN_MIGRATIONS_ON_START=true`.

**Race condition analysis**: On Render Free with a single web service, there's only one container. Migrations run in the entrypoint before gunicorn starts. Even if the container restarts, only one entrypoint runs at a time. **No migration race on a single-service free plan.**

On paid plans with multiple instances: Alembic acquires a PostgreSQL advisory lock during migration. The `alembic_version` table provides serialization. **Safe under multiple instances.**

### Target database verification

The entrypoint runs in the same container environment as the app. It uses `DATABASE_MIGRATION_URL` (or `DATABASE_URL` fallback) from the Render environment. **It cannot accidentally connect to a local Docker hostname** because:
1. No Docker network exists on Render
2. The env var is set to a Neon hostname
3. `localhost:5432` would fail (no local PostgreSQL)

### RLS preservation

**Source**: `app/db/tenant.py`

Migrations run as the migrator role, which owns the schema. RLS policies are defined in migration files and enforced on the runtime role. Alembic `upgrade head` does not disable RLS — it only applies DDL. **RLS remains intact.**

## Confirmed Facts

| Check | Result |
|-------|--------|
| Local Docker PostgreSQL used only for dev | YES — docker-compose.yml defines a `db` service for local dev |
| Render config creates no database | YES — no `databases:` section in render.yaml |
| DATABASE_URL is manually set | YES — `sync: false` |
| Default DATABASE_URL fails safely | YES — connects to localhost, health check fails, service not ready |
| Migration uses correct Alembic env | YES — `migrations/env.py` reads from Settings |
| Migration connection uses NullPool | YES — `migrations/env.py:26` |
| RLS policies survive migration | YES — DDL-only, no RLS disable |
| ClientCursor compatible with Neon pooler | YES — no server-side prepared statements |

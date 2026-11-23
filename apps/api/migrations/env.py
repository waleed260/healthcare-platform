from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings

config = context.config
settings = get_settings()
# Migrations run as the schema owner (DATABASE_MIGRATION_URL) when it is set; the app role cannot alter schema.
migration_url = settings.database_migration_url or settings.database_url
config.set_main_option("sqlalchemy.url", migration_url.replace("%", "%%"))
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def run_migrations_offline() -> None:
    context.configure(url=migration_url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            # Some revision ids exceed Alembic's default version_num varchar(32)
            # (e.g. 0069_patient_transfers_discharges, 33 chars), so a fresh DB
            # fails to stamp them. Ensure the column is wide enough first:
            # CREATE covers a fresh DB (Alembic then reuses this table), ALTER
            # widens an existing varchar(32) DB in place. Both idempotent.
            connection.exec_driver_sql(
                "CREATE TABLE IF NOT EXISTS alembic_version "
                "(version_num VARCHAR(64) NOT NULL, "
                "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
            )
            connection.exec_driver_sql(
                "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)"
            )
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

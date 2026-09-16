"""Add optimistic-locking and archive fields to rooms and resources."""
from alembic import op


revision = "0028_catalog_resource_lifecycle"
down_revision = "0027_website_preview_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("rooms", "resources"):
        op.execute(f"ALTER TABLE {table} ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now()")
        op.execute(f"ALTER TABLE {table} ADD COLUMN archived_at timestamptz NULL")
        op.execute(f"ALTER TABLE {table} ADD COLUMN version integer NOT NULL DEFAULT 1 CHECK (version > 0)")
        op.execute(f"CREATE INDEX ix_{table}_active ON {table} (clinic_id, branch_id, name) WHERE archived_at IS NULL")


def downgrade() -> None:
    for table in ("resources", "rooms"):
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_active")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS version")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS archived_at")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS updated_at")

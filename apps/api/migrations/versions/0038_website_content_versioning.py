"""Add optimistic versions to editable website pages and sections."""

from alembic import op


revision = "0038_website_content_versioning"
down_revision = "0037_safe_tenant_policy_cast"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("website_pages", "website_sections"):
        op.execute(f"ALTER TABLE {table} ADD COLUMN version integer NOT NULL DEFAULT 1 CHECK (version > 0)")


def downgrade() -> None:
    for table in ("website_sections", "website_pages"):
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS version")

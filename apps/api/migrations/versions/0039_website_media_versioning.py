"""Add optimistic versions to editable website media metadata."""

from alembic import op


revision = "0039_website_media_versioning"
down_revision = "0038_website_content_versioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE website_media ADD COLUMN version integer NOT NULL DEFAULT 1 CHECK (version > 0)")


def downgrade() -> None:
    op.execute("ALTER TABLE website_media DROP COLUMN IF EXISTS version")

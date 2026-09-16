"""Store integrity metadata for uploaded website media."""
from alembic import op
import sqlalchemy as sa


revision = "0031_website_media_uploads"
down_revision = "0030_document_download_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("website_media", sa.Column("original_filename", sa.Text(), nullable=True))
    op.add_column("website_media", sa.Column("size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("website_media", sa.Column("content_sha256", sa.Text(), nullable=True))
    op.add_column("website_media", sa.Column("scan_failure_reason", sa.Text(), nullable=True))
    op.execute("CREATE INDEX ix_website_media_scan_status ON website_media (clinic_id, scan_status, created_at)")


def downgrade() -> None:
    op.drop_index("ix_website_media_scan_status", table_name="website_media")
    op.drop_column("website_media", "scan_failure_reason")
    op.drop_column("website_media", "content_sha256")
    op.drop_column("website_media", "size_bytes")
    op.drop_column("website_media", "original_filename")

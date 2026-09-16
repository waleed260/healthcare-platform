"""Retain bounded, operator-entered identity-verification evidence."""
from alembic import op
import sqlalchemy as sa


revision = "0034_privacy_identity_evidence"
down_revision = "0033_website_media_scan_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("privacy_requests", sa.Column("identity_verification_evidence", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("privacy_requests", "identity_verification_evidence")

"""Allow document access telemetry to distinguish actual downloads."""
from alembic import op


revision = "0030_document_download_audit"
down_revision = "0029_clinic_onboarding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE document_access_events DROP CONSTRAINT ck_document_access_action")
    op.execute("ALTER TABLE document_access_events ADD CONSTRAINT ck_document_access_action CHECK (action IN ('metadata_read', 'signed_access_issued', 'downloaded', 'archived'))")


def downgrade() -> None:
    raise RuntimeError("0030 cannot be downgraded after download audit records may exist")

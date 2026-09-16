"""Add privacy-safe audit records for patient document access."""
from alembic import op


revision = "0019_document_access_audit"
down_revision = "0018_feature_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE document_access_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            document_id uuid NOT NULL,
            user_id uuid NOT NULL,
            action text NOT NULL,
            request_id uuid NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_document_access_events_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_document_access_action CHECK (action IN ('metadata_read', 'signed_access_issued', 'archived')),
            FOREIGN KEY (clinic_id, document_id) REFERENCES patient_documents (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    op.execute("ALTER TABLE document_access_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE document_access_events FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY document_access_events_tenant_policy ON document_access_events
        USING (clinic_id = current_setting('app.clinic_id', true)::uuid)
        WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)
    """)
    op.execute("CREATE INDEX ix_document_access_events_document ON document_access_events (clinic_id, document_id, created_at DESC)")
    op.execute("GRANT SELECT, INSERT ON document_access_events TO healthcare_runtime")


def downgrade() -> None:
    op.drop_index("ix_document_access_events_document", table_name="document_access_events")
    op.execute("DROP TABLE IF EXISTS document_access_events")

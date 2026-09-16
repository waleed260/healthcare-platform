"""Create private patient-document metadata and scan event records."""
from alembic import op
import sqlalchemy as sa

revision = "0010_private_files"
down_revision = "0009_crm_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for code, description in (
        ("patient.document.read", "Read patient document metadata and clean downloads"),
        ("patient.document.write", "Upload patient documents"),
        ("patient.document.delete", "Archive patient documents"),
    ):
        op.execute(sa.text("INSERT INTO permissions (code, description) VALUES (:code, :description) ON CONFLICT (code) DO NOTHING").bindparams(code=code, description=description))
    for role, codes in {
        "owner": ("patient.document.read", "patient.document.write", "patient.document.delete"),
        "manager": ("patient.document.read", "patient.document.write", "patient.document.delete"),
        "doctor": ("patient.document.read", "patient.document.write"),
        "receptionist": ("patient.document.read",),
    }.items():
        for code in codes:
            op.execute(sa.text("""
                INSERT INTO role_permissions (role_id, permission_code)
                SELECT r.id, :code FROM roles r WHERE r.name = :role ON CONFLICT DO NOTHING
            """).bindparams(role=role, code=code))
    op.execute("""
        CREATE TABLE patient_documents (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            patient_id uuid NOT NULL,
            uploaded_by_user_id uuid NOT NULL,
            storage_key text NOT NULL,
            original_filename text NOT NULL,
            mime_type text NOT NULL,
            size_bytes bigint NOT NULL,
            content_sha256 char(64) NOT NULL,
            scan_status text NOT NULL DEFAULT 'pending_scan',
            scan_failure_reason text NULL,
            retention_class text NOT NULL DEFAULT 'standard',
            legal_hold boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            version integer NOT NULL DEFAULT 1,
            CONSTRAINT uq_patient_documents_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT uq_patient_documents_storage_key UNIQUE (storage_key),
            CONSTRAINT ck_patient_documents_size CHECK (size_bytes > 0 AND size_bytes <= 20971520),
            CONSTRAINT ck_patient_documents_scan_status CHECK (scan_status IN ('pending_scan', 'clean', 'quarantined', 'scan_failed')),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES patients (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, uploaded_by_user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE TABLE file_scan_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            document_id uuid NOT NULL,
            engine text NOT NULL,
            signature_version text NOT NULL,
            outcome text NOT NULL,
            failure_reason text NULL,
            scanned_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_file_scan_events_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_file_scan_events_outcome CHECK (outcome IN ('clean', 'quarantined', 'scan_failed')),
            FOREIGN KEY (clinic_id, document_id) REFERENCES patient_documents (clinic_id, id) ON DELETE CASCADE
        )
    """)
    for table in ("patient_documents", "file_scan_events"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(sa.text(f"CREATE POLICY {table}_tenant_policy ON {table} USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)"))
    op.execute("CREATE INDEX ix_patient_documents_patient ON patient_documents (clinic_id, patient_id, archived_at, created_at)")
    op.execute("CREATE INDEX ix_patient_documents_scan_status ON patient_documents (clinic_id, scan_status, created_at)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON patient_documents, file_scan_events TO healthcare_runtime")


def downgrade() -> None:
    op.drop_index("ix_patient_documents_scan_status", table_name="patient_documents")
    op.drop_index("ix_patient_documents_patient", table_name="patient_documents")
    op.execute("DROP TABLE IF EXISTS file_scan_events")
    op.execute("DROP TABLE IF EXISTS patient_documents")

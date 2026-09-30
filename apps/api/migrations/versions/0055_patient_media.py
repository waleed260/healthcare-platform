"""Add tenant-scoped clinical media with explicit website approval."""
from alembic import op
import sqlalchemy as sa


revision = "0055_patient_media"
down_revision = "0054_website_section_library"
branch_labels = None
depends_on = None


def upgrade() -> None:
    permissions = (
        ("patient.media.read", "Read patient clinical media metadata"),
        ("patient.media.write", "Upload patient clinical media"),
        ("patient.media.approve", "Approve or revoke patient media for website use"),
    )
    for code, description in permissions:
        op.execute(sa.text("INSERT INTO permissions (code, description) VALUES (:code, :description) ON CONFLICT (code) DO NOTHING").bindparams(code=code, description=description))
    role_codes = {
        "owner": tuple(code for code, _ in permissions),
        "manager": tuple(code for code, _ in permissions),
        "doctor": ("patient.media.read", "patient.media.write"),
        "receptionist": ("patient.media.read",),
    }
    for role, codes in role_codes.items():
        for code in codes:
            op.execute(sa.text("""
                INSERT INTO role_permissions (role_id, permission_code)
                SELECT r.id, :code FROM roles r WHERE r.name = :role ON CONFLICT DO NOTHING
            """).bindparams(role=role, code=code))
    op.execute("""
        CREATE TABLE patient_media (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            patient_id uuid NOT NULL,
            treatment_plan_item_id uuid NULL,
            provider_user_id uuid NULL,
            captured_on date NOT NULL DEFAULT CURRENT_DATE,
            media_kind text NOT NULL DEFAULT 'other',
            storage_key text NOT NULL,
            original_filename text NOT NULL,
            mime_type text NOT NULL,
            size_bytes bigint NOT NULL,
            content_sha256 text NOT NULL,
            scan_status text NOT NULL DEFAULT 'pending_scan',
            scan_failure_reason text NULL,
            approval_status text NOT NULL DEFAULT 'pending',
            approved_for_website boolean NOT NULL DEFAULT false,
            consent_record_id uuid NULL,
            approved_by_user_id uuid NULL,
            approved_at timestamptz NULL,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            CONSTRAINT uq_patient_media_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT uq_patient_media_storage_key UNIQUE (storage_key),
            CONSTRAINT ck_patient_media_kind CHECK (media_kind IN ('before', 'after', 'other')),
            CONSTRAINT ck_patient_media_mime CHECK (mime_type IN ('image/jpeg', 'image/png', 'image/webp')),
            CONSTRAINT ck_patient_media_size CHECK (size_bytes > 0 AND size_bytes <= 8388608),
            CONSTRAINT ck_patient_media_sha CHECK (content_sha256 ~ '^[0-9a-fA-F]{64}$'),
            CONSTRAINT ck_patient_media_scan CHECK (scan_status IN ('pending_scan', 'clean', 'quarantined', 'scan_failed')),
            CONSTRAINT ck_patient_media_approval CHECK (approval_status IN ('pending', 'approved', 'revoked')),
            CONSTRAINT ck_patient_media_approval_pair CHECK (approved_for_website = (approval_status = 'approved')),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES patients (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, treatment_plan_item_id) REFERENCES treatment_plan_items (clinic_id, id) ON DELETE SET NULL,
            FOREIGN KEY (clinic_id, provider_user_id) REFERENCES users (clinic_id, id) ON DELETE SET NULL,
            FOREIGN KEY (clinic_id, consent_record_id) REFERENCES consent_records (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, approved_by_user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE TABLE patient_media_scan_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            media_id uuid NOT NULL,
            engine text NOT NULL,
            signature_version text NOT NULL,
            outcome text NOT NULL,
            failure_reason text NULL,
            scanned_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_patient_media_scan_events_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_patient_media_scan_outcome CHECK (outcome IN ('clean', 'quarantined', 'scan_failed')),
            FOREIGN KEY (clinic_id, media_id) REFERENCES patient_media (clinic_id, id) ON DELETE CASCADE
        )
    """)
    for table in ("patient_media", "patient_media_scan_events"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(sa.text(f"CREATE POLICY {table}_tenant_policy ON {table} USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)"))
    op.execute("CREATE INDEX ix_patient_media_patient ON patient_media (clinic_id, patient_id, archived_at, captured_on DESC, id DESC)")
    op.execute("CREATE INDEX ix_patient_media_website_approval ON patient_media (clinic_id, approved_for_website, approval_status, scan_status)")
    op.execute("CREATE INDEX ix_patient_media_scan_status ON patient_media (clinic_id, scan_status, created_at)")
    op.execute("CREATE INDEX ix_patient_media_scan_events_media ON patient_media_scan_events (clinic_id, media_id, scanned_at DESC)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON patient_media, patient_media_scan_events TO healthcare_runtime")


def downgrade() -> None:
    for index in ("ix_patient_media_scan_events_media", "ix_patient_media_scan_status", "ix_patient_media_website_approval", "ix_patient_media_patient"):
        op.drop_index(index, table_name="patient_media_scan_events" if index == "ix_patient_media_scan_events_media" else "patient_media")
    op.execute("DROP TABLE IF EXISTS patient_media_scan_events")
    op.execute("DROP TABLE IF EXISTS patient_media")

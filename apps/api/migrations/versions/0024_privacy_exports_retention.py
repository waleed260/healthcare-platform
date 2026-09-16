"""Add retention policy configuration and privacy-safe export jobs."""
from alembic import op
import sqlalchemy as sa

revision = "0024_privacy_exports_retention"
down_revision = "0023_governance_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("privacy_requests", sa.Column("identity_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("privacy_requests", sa.Column("identity_verified_by_user_id", sa.Uuid(), nullable=True))
    op.add_column("privacy_requests", sa.Column("legal_hold_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("privacy_requests", sa.Column("completion_evidence", sa.Text(), nullable=True))
    op.create_foreign_key("fk_privacy_identity_verifier", "privacy_requests", "users", ["clinic_id", "identity_verified_by_user_id"], ["clinic_id", "id"], ondelete="RESTRICT")
    op.execute("""
        CREATE TABLE retention_policies (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            name text NOT NULL,
            jurisdiction text NOT NULL,
            rules jsonb NOT NULL DEFAULT '{}'::jsonb,
            approved_by text NULL,
            approved_at timestamptz NULL,
            active boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_retention_policy_approval CHECK ((active = false) OR (approved_by IS NOT NULL AND approved_at IS NOT NULL))
        )
    """)
    op.add_column("clinics", sa.Column("retention_policy_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_clinics_retention_policy", "clinics", "retention_policies", ["retention_policy_id"], ["id"], ondelete="RESTRICT")
    op.execute("""
        CREATE TABLE export_jobs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            requested_by_user_id uuid,
            patient_id uuid,
            privacy_request_id uuid,
            export_type text NOT NULL,
            status text NOT NULL DEFAULT 'queued',
            storage_key text NULL,
            download_token_hash char(64) NULL,
            expires_at timestamptz NULL,
            failure_code text NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            completed_at timestamptz NULL,
            CONSTRAINT uq_export_jobs_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_export_jobs_type CHECK (export_type IN ('patient_access', 'audit')),
            CONSTRAINT ck_export_jobs_status CHECK (status IN ('queued', 'running', 'completed', 'failed', 'expired')),
            FOREIGN KEY (clinic_id, requested_by_user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, patient_id) REFERENCES patients (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, privacy_request_id) REFERENCES privacy_requests (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    op.execute("ALTER TABLE export_jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE export_jobs FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY export_jobs_tenant_policy ON export_jobs
        USING (clinic_id = current_setting('app.clinic_id', true)::uuid)
        WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)
    """)
    op.execute("CREATE INDEX ix_export_jobs_clinic_status ON export_jobs (clinic_id, status, created_at DESC)")
    op.execute("GRANT SELECT, INSERT, UPDATE ON retention_policies, export_jobs TO healthcare_runtime")


def downgrade() -> None:
    op.drop_index("ix_export_jobs_clinic_status", table_name="export_jobs")
    op.execute("DROP TABLE IF EXISTS export_jobs")
    op.drop_constraint("fk_clinics_retention_policy", "clinics", type_="foreignkey")
    op.drop_column("clinics", "retention_policy_id")
    op.execute("DROP TABLE IF EXISTS retention_policies")
    op.drop_constraint("fk_privacy_identity_verifier", "privacy_requests", type_="foreignkey")
    for column in ("completion_evidence", "legal_hold_checked_at", "identity_verified_by_user_id", "identity_verified_at"):
        op.drop_column("privacy_requests", column)

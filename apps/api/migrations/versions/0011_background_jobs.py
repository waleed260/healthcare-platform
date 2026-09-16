"""Add idempotent database-backed job and notification provenance records."""
from alembic import op
import sqlalchemy as sa

revision = "0011_background_jobs"
down_revision = "0010_private_files"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("source_job_key", sa.Text(), nullable=True))
    op.execute("""
        CREATE UNIQUE INDEX uq_notifications_job_recipient
        ON notifications (clinic_id, user_id, source_job_key)
        WHERE source_job_key IS NOT NULL
    """)
    op.execute("""
        CREATE TABLE background_jobs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            job_key text NOT NULL,
            job_type text NOT NULL,
            status text NOT NULL DEFAULT 'queued',
            available_at timestamptz NOT NULL DEFAULT now(),
            locked_at timestamptz NULL,
            attempts integer NOT NULL DEFAULT 0,
            last_error text NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_background_jobs_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT uq_background_jobs_key UNIQUE (clinic_id, job_key),
            CONSTRAINT ck_background_jobs_status CHECK (status IN ('queued', 'running', 'completed', 'failed')),
            FOREIGN KEY (clinic_id) REFERENCES clinics (id) ON DELETE CASCADE
        )
    """)
    op.execute("ALTER TABLE background_jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE background_jobs FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY background_jobs_tenant_policy ON background_jobs USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)")
    op.execute("CREATE INDEX ix_background_jobs_ready ON background_jobs (clinic_id, status, available_at)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON background_jobs TO healthcare_runtime")


def downgrade() -> None:
    op.drop_index("ix_background_jobs_ready", table_name="background_jobs")
    op.execute("DROP TABLE IF EXISTS background_jobs")
    op.execute("DROP INDEX IF EXISTS uq_notifications_job_recipient")
    op.drop_column("notifications", "source_job_key")

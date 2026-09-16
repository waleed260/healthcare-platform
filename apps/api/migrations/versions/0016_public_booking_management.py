"""Add public appointment reschedule requests for management-token flows."""
from alembic import op

revision = "0016_public_booking_management"
down_revision = "0015_website_publishing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE appointment_reschedule_requests (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            appointment_id uuid NOT NULL,
            requested_starts_at timestamptz NOT NULL,
            reason text NOT NULL,
            status text NOT NULL DEFAULT 'pending',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_appointment_reschedule_requests_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_reschedule_request_status CHECK (status IN ('pending', 'reviewed', 'accepted', 'rejected')),
            FOREIGN KEY (clinic_id, appointment_id) REFERENCES appointments (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("ALTER TABLE appointment_reschedule_requests ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE appointment_reschedule_requests FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY appointment_reschedule_requests_tenant_policy ON appointment_reschedule_requests USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)")
    op.execute("CREATE INDEX ix_reschedule_requests_appointment ON appointment_reschedule_requests (clinic_id, appointment_id, status, created_at)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON appointment_reschedule_requests TO healthcare_runtime")


def downgrade() -> None:
    op.drop_index("ix_reschedule_requests_appointment", table_name="appointment_reschedule_requests")
    op.execute("DROP TABLE IF EXISTS appointment_reschedule_requests")

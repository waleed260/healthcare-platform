"""Self-service staff access requests: a clinic-scoped approval queue that feeds
the existing staff-invitation flow. A pending request grants NO access; an
authorized admin (staff.manage) approves it, which issues a normal staff
invitation with the admin-chosen role, or rejects it. Reuses the existing RBAC,
invitation, tenant-isolation (RLS) and audit systems — no new auth model.
"""
from alembic import op

revision = "0098_access_requests"
down_revision = "0097_saved_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE access_requests (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            normalized_email text NOT NULL,
            display_name text NULL,
            requested_role text NULL,          -- requester's hint only; the admin decides the real role
            reason text NULL,
            status text NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'approved', 'rejected', 'expired', 'revoked')),
            decided_by_user_id uuid NULL,
            decided_at timestamptz NULL,
            decision_note text NULL,           -- internal admin note; never shown to the requester
            invitation_id uuid NULL,           -- set when approved (soft reference to staff_invitations)
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_access_requests_clinic_id UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id) REFERENCES clinics (id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, decided_by_user_id) REFERENCES users (clinic_id, id) ON DELETE SET NULL
        )
    """)
    op.execute("ALTER TABLE access_requests ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE access_requests FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY access_requests_tenant_policy ON access_requests "
               "USING (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid) "
               "WITH CHECK (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid)")
    # Queue ordering for the admin review list.
    op.execute("CREATE INDEX ix_access_requests_clinic_status ON access_requests (clinic_id, status, created_at DESC)")
    # Duplicate-request protection: at most one OPEN (pending) request per email per clinic.
    op.execute("CREATE UNIQUE INDEX uq_access_requests_pending_email "
               "ON access_requests (clinic_id, normalized_email) WHERE status = 'pending'")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON access_requests TO healthcare_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS access_requests")

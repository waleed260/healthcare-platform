"""Actionable follow-up tasks for leads (distinct from the immutable lead_activities log).

A lead follow-up is a dated, assignable task with a pending -> completed/cancelled lifecycle;
"overdue" is derived (pending and past due). Kept separate from the patient-bound
``follow_up_tasks`` table so the patient-recall funnel is untouched. Tenant-forced RLS; runtime
may read, insert and update (never hard-delete — cancellation is a status).
"""
from alembic import op

revision = "0103_lead_follow_ups"
down_revision = "0102_leads_capture_method"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE lead_follow_ups (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            lead_id uuid NOT NULL,
            description text NOT NULL,
            due_at timestamptz NOT NULL,
            assigned_to_user_id uuid NULL,
            status text NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'completed', 'cancelled')),
            completed_at timestamptz NULL,
            completed_by_user_id uuid NULL,
            created_by_user_id uuid NOT NULL,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_lead_follow_ups_body CHECK (length(btrim(description)) BETWEEN 1 AND 2000),
            CONSTRAINT uq_lead_follow_ups_clinic_id UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, lead_id) REFERENCES leads (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, assigned_to_user_id) REFERENCES users (clinic_id, id) ON DELETE SET NULL,
            FOREIGN KEY (clinic_id, completed_by_user_id) REFERENCES users (clinic_id, id) ON DELETE SET NULL,
            FOREIGN KEY (clinic_id, created_by_user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    op.execute("ALTER TABLE lead_follow_ups ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE lead_follow_ups FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY lead_follow_ups_tenant_policy ON lead_follow_ups "
               "USING (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid) "
               "WITH CHECK (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid)")
    op.execute("CREATE INDEX ix_lead_follow_ups_lead ON lead_follow_ups (clinic_id, lead_id, due_at)")
    op.execute("CREATE INDEX ix_lead_follow_ups_open ON lead_follow_ups (clinic_id, due_at) WHERE status = 'pending'")
    op.execute("GRANT SELECT, INSERT, UPDATE ON lead_follow_ups TO healthcare_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lead_follow_ups")

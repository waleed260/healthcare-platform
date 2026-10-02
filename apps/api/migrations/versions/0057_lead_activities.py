"""Add immutable, tenant-isolated lead activity and dated follow-up history."""

from alembic import op


revision = "0057_lead_activities"
down_revision = "0056_clinical_forms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE lead_activities (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            lead_id uuid NOT NULL,
            actor_user_id uuid NOT NULL,
            kind text NOT NULL,
            body text NOT NULL,
            due_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_lead_activities_kind
                CHECK (kind IN ('call', 'note', 'message', 'follow_up')),
            CONSTRAINT ck_lead_activities_body
                CHECK (length(btrim(body)) BETWEEN 1 AND 5000),
            CONSTRAINT ck_lead_activities_due_at
                CHECK ((kind = 'follow_up') = (due_at IS NOT NULL)),
            FOREIGN KEY (clinic_id, lead_id)
                REFERENCES leads (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, actor_user_id)
                REFERENCES users (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE INDEX ix_lead_activities_history
        ON lead_activities (clinic_id, lead_id, created_at DESC, id DESC)
    """)
    op.execute("""
        CREATE INDEX ix_lead_activities_follow_up
        ON lead_activities (clinic_id, due_at) WHERE kind = 'follow_up'
    """)
    op.execute("ALTER TABLE lead_activities ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE lead_activities FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY lead_activities_tenant_policy ON lead_activities
        USING (clinic_id = current_setting('app.clinic_id', true)::uuid)
        WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)
    """)
    op.execute("GRANT SELECT, INSERT ON lead_activities TO healthcare_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE lead_activities")

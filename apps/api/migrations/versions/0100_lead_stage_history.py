"""Immutable per-lead stage history (mirrors appointment_history).

Every lead stage change — manual or event-driven (booking, arrival, cancellation, conversion,
lost/reopen) — appends one row here, so the lead detail page and audits have a queryable timeline
rather than only scattered generic audit events. Tenant-forced RLS; runtime may read and append
only. Existing leads are backfilled with one synthetic row capturing their current stage.
"""
from alembic import op

revision = "0100_lead_stage_history"
down_revision = "0099_appointments_lead_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE lead_stage_history (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            lead_id uuid NOT NULL,
            from_status text NULL,
            to_status text NOT NULL,
            actor_user_id uuid NULL,
            reason text NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_lead_stage_history_clinic_id UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, lead_id) REFERENCES leads (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, actor_user_id) REFERENCES users (clinic_id, id) ON DELETE SET NULL
        )
    """)
    op.execute("ALTER TABLE lead_stage_history ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE lead_stage_history FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY lead_stage_history_tenant_policy ON lead_stage_history "
               "USING (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid) "
               "WITH CHECK (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid)")
    op.execute("CREATE INDEX ix_lead_stage_history_timeline "
               "ON lead_stage_history (clinic_id, lead_id, created_at DESC, id DESC)")
    op.execute("GRANT SELECT, INSERT ON lead_stage_history TO healthcare_runtime")
    # Backfill: one row per existing lead, timestamped at the lead's creation, so the timeline
    # is not empty for pre-existing leads. NULL actor = system backfill.
    op.execute("""
        INSERT INTO lead_stage_history (clinic_id, lead_id, from_status, to_status, reason, created_at)
        SELECT clinic_id, id, NULL, status, 'backfill', created_at FROM leads
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lead_stage_history")

"""Per-patient structured state for specialty clinical tools (dental chart, Norwood, grafts, skin map)."""
from alembic import op

revision = "0066_clinical_tool_states"
down_revision = "0065_safe_tenant_cast"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE clinical_tool_states (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            patient_id uuid NOT NULL,
            tool_key text NOT NULL CHECK (tool_key IN ('dental_chart', 'norwood', 'graft_plan', 'skin_map')),
            state jsonb NOT NULL DEFAULT '{}'::jsonb,
            version integer NOT NULL DEFAULT 1,
            updated_by_user_id uuid NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_clinical_tool_states_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT uq_clinical_tool_states_patient_tool UNIQUE (clinic_id, patient_id, tool_key),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES patients (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("ALTER TABLE clinical_tool_states ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE clinical_tool_states FORCE ROW LEVEL SECURITY")
    # NULLIF guard so an empty tenant context never casts '' to uuid (see migration 0065).
    op.execute("CREATE POLICY clinical_tool_states_tenant_policy ON clinical_tool_states USING (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid) WITH CHECK (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON clinical_tool_states TO healthcare_runtime")
    op.execute("CREATE INDEX ix_clinical_tool_states_patient ON clinical_tool_states (clinic_id, patient_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS clinical_tool_states")

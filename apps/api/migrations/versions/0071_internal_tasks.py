"""Add internal_tasks table for clinic task management."""

revision = "0071_internal_tasks"
down_revision = "0070_patient_extended_fields"

from alembic import op


def upgrade() -> None:
    op.execute("""
        CREATE TABLE internal_tasks (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            title text NOT NULL,
            description text NULL,
            task_type text NOT NULL DEFAULT 'general',
            priority text NOT NULL DEFAULT 'normal',
            status text NOT NULL DEFAULT 'open',
            assignee_user_id uuid NULL,
            patient_id uuid NULL,
            lead_id uuid NULL,
            appointment_id uuid NULL,
            due_at timestamptz NULL,
            completed_at timestamptz NULL,
            created_by uuid NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            version integer NOT NULL DEFAULT 1,
            CONSTRAINT uq_internal_tasks_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_internal_tasks_type CHECK (task_type IN ('general', 'follow_up', 'callback', 'review', 'billing', 'clinical', 'admin')),
            CONSTRAINT ck_internal_tasks_priority CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
            CONSTRAINT ck_internal_tasks_status CHECK (status IN ('open', 'in_progress', 'completed', 'cancelled'))
        )
    """)
    op.execute("CREATE INDEX ix_internal_tasks_clinic ON internal_tasks (clinic_id, archived_at, status, due_at)")
    op.execute("CREATE INDEX ix_internal_tasks_assignee ON internal_tasks (clinic_id, assignee_user_id, archived_at, status)")
    op.execute("ALTER TABLE internal_tasks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE internal_tasks FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY internal_tasks_tenant ON internal_tasks USING (clinic_id = current_setting('app.current_tenant')::uuid)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON internal_tasks TO healthcare_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS internal_tasks")

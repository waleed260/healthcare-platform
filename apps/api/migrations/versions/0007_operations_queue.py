"""Create reception queue, follow-ups, and in-app notifications."""
from alembic import op
import sqlalchemy as sa

revision = "0007_operations_queue"
down_revision = "0006_appointments_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for code, description in (("queue.read", "Read the reception queue"), ("queue.manage", "Manage the reception queue"), ("followup.read", "Read follow-up tasks"), ("followup.manage", "Manage follow-up tasks"), ("notification.read", "Read notifications"), ("notification.manage", "Manage notifications")):
        op.execute(sa.text("INSERT INTO permissions (code, description) VALUES (:code, :description) ON CONFLICT (code) DO NOTHING").bindparams(code=code, description=description))
    for role in ("owner", "manager", "doctor", "receptionist"):
        op.execute(sa.text("""
            INSERT INTO role_permissions (role_id, permission_code)
            SELECT r.id, p.code FROM roles r CROSS JOIN permissions p
            WHERE r.name = :role AND p.code IN ('queue.read', 'queue.manage', 'followup.read', 'followup.manage', 'notification.read', 'notification.manage')
        """).bindparams(role=role))
    op.execute("""
        CREATE TABLE queue_entries (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            appointment_id uuid NOT NULL,
            status text NOT NULL DEFAULT 'waiting',
            checked_in_at timestamptz NOT NULL DEFAULT now(),
            priority integer NOT NULL DEFAULT 0,
            priority_reason text NULL,
            started_at timestamptz NULL,
            completed_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_queue_entries_clinic_id UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, appointment_id) REFERENCES appointments (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("CREATE UNIQUE INDEX uq_queue_active_appointment ON queue_entries (clinic_id, appointment_id) WHERE status IN ('waiting', 'in_consultation')")
    op.execute("""
        CREATE TABLE follow_up_tasks (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            patient_id uuid NOT NULL,
            appointment_id uuid NULL,
            assignee_user_id uuid NULL,
            reason text NOT NULL,
            due_at timestamptz NOT NULL,
            priority text NOT NULL DEFAULT 'normal',
            status text NOT NULL DEFAULT 'due',
            outcome_note text NULL,
            completed_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_follow_up_tasks_clinic_id UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES patients (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, appointment_id) REFERENCES appointments (clinic_id, id) ON DELETE SET NULL
        )
    """)
    op.execute("""
        CREATE TABLE notifications (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            user_id uuid NOT NULL,
            kind text NOT NULL,
            title text NOT NULL,
            body text NOT NULL,
            read_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_notifications_clinic_id UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, user_id) REFERENCES users (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE browser_push_subscriptions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            user_id uuid NOT NULL,
            endpoint text NOT NULL,
            encrypted_credentials text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            revoked_at timestamptz NULL,
            CONSTRAINT uq_push_subscription_endpoint UNIQUE (endpoint),
            FOREIGN KEY (clinic_id, user_id) REFERENCES users (clinic_id, id) ON DELETE CASCADE
        )
    """)
    for table in ("queue_entries", "follow_up_tasks", "notifications", "browser_push_subscriptions"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(sa.text(f"""
            CREATE POLICY {table}_tenant_policy ON {table}
            USING (clinic_id = current_setting('app.clinic_id', true)::uuid)
            WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)
        """))
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON queue_entries, follow_up_tasks, notifications, browser_push_subscriptions TO healthcare_runtime")


def downgrade() -> None:
    for table in ("browser_push_subscriptions", "notifications", "follow_up_tasks", "queue_entries"):
        op.execute(f"DROP TABLE IF EXISTS {table}")

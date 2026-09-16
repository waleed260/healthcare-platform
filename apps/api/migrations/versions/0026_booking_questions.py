"""Add tenant-scoped booking questions and appointment answers."""
from alembic import op

revision = "0026_booking_questions"
down_revision = "0025_staff_invitation_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE booking_questions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(), clinic_id uuid NOT NULL,
            prompt text NOT NULL, input_type text NOT NULL, options jsonb NOT NULL DEFAULT '[]'::jsonb,
            required boolean NOT NULL DEFAULT false, active boolean NOT NULL DEFAULT true,
            version integer NOT NULL DEFAULT 1, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_booking_questions_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_booking_questions_type CHECK (input_type IN ('text', 'yes_no', 'choice')),
            CONSTRAINT ck_booking_questions_options CHECK ((input_type = 'choice' AND jsonb_array_length(options) BETWEEN 1 AND 20) OR (input_type <> 'choice' AND options = '[]'::jsonb)),
            FOREIGN KEY (clinic_id) REFERENCES clinics(id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE service_booking_questions (
            clinic_id uuid NOT NULL, service_id uuid NOT NULL, question_id uuid NOT NULL,
            position integer NOT NULL CHECK (position >= 0), PRIMARY KEY (clinic_id, service_id, question_id),
            UNIQUE (clinic_id, service_id, position),
            FOREIGN KEY (clinic_id, service_id) REFERENCES services (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, question_id) REFERENCES booking_questions (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE appointment_answers (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(), clinic_id uuid NOT NULL, appointment_id uuid NOT NULL,
            question_id uuid NOT NULL, answer jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_appointment_answers_question UNIQUE (clinic_id, appointment_id, question_id),
            FOREIGN KEY (clinic_id, appointment_id) REFERENCES appointments (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, question_id) REFERENCES booking_questions (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    for table in ("booking_questions", "service_booking_questions", "appointment_answers"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_tenant_policy ON {table} USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)")
    op.execute("CREATE INDEX ix_service_booking_questions_lookup ON service_booking_questions (clinic_id, service_id, position)")
    op.execute("CREATE INDEX ix_appointment_answers_appointment ON appointment_answers (clinic_id, appointment_id)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON booking_questions, service_booking_questions, appointment_answers TO healthcare_runtime")


def downgrade() -> None:
    op.drop_index("ix_appointment_answers_appointment", table_name="appointment_answers")
    op.drop_index("ix_service_booking_questions_lookup", table_name="service_booking_questions")
    for table in ("appointment_answers", "service_booking_questions", "booking_questions"):
        op.execute(f"DROP TABLE IF EXISTS {table}")

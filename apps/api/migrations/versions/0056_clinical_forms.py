"""Add specialty-scoped clinical form templates and patient responses."""
from alembic import op
import sqlalchemy as sa


revision = "0056_clinical_forms"
down_revision = "0055_patient_media"
branch_labels = None
depends_on = None


def upgrade() -> None:
    permissions = (
        ("clinical.form.read", "Read specialty-specific clinical forms"),
        ("clinical.form.manage", "Manage specialty-specific clinical forms and responses"),
    )
    for code, description in permissions:
        op.execute(sa.text("INSERT INTO permissions (code, description) VALUES (:code, :description) ON CONFLICT (code) DO NOTHING").bindparams(code=code, description=description))
    for role, codes in {
        "owner": ("clinical.form.read", "clinical.form.manage"),
        "manager": ("clinical.form.read", "clinical.form.manage"),
        "doctor": ("clinical.form.read", "clinical.form.manage"),
        "receptionist": ("clinical.form.read",),
    }.items():
        for code in codes:
            op.execute(sa.text("""
                INSERT INTO role_permissions (role_id, permission_code)
                SELECT r.id, :code FROM roles r WHERE r.name = :role ON CONFLICT DO NOTHING
            """).bindparams(role=role, code=code))
    op.execute("""
        CREATE TABLE clinical_form_templates (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            specialty_id uuid NULL,
            form_key text NOT NULL,
            name text NOT NULL,
            field_schema jsonb NOT NULL DEFAULT '{}'::jsonb,
            status text NOT NULL DEFAULT 'active',
            version integer NOT NULL DEFAULT 1,
            created_by_user_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            CONSTRAINT uq_clinical_form_templates_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT uq_clinical_form_templates_key UNIQUE (clinic_id, form_key),
            CONSTRAINT ck_clinical_form_templates_status CHECK (status IN ('active', 'archived')),
            FOREIGN KEY (clinic_id) REFERENCES clinics (id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, specialty_id) REFERENCES clinic_specialties (clinic_id, specialty_id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, created_by_user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE TABLE clinical_form_responses (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            patient_id uuid NOT NULL,
            template_id uuid NOT NULL,
            appointment_id uuid NULL,
            response_data jsonb NOT NULL DEFAULT '{}'::jsonb,
            status text NOT NULL DEFAULT 'draft',
            submitted_at timestamptz NULL,
            submitted_by_user_id uuid NULL,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_clinical_form_responses_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_clinical_form_responses_status CHECK (status IN ('draft', 'submitted')),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES patients (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, template_id) REFERENCES clinical_form_templates (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, appointment_id) REFERENCES appointments (clinic_id, id) ON DELETE SET NULL,
            FOREIGN KEY (clinic_id, submitted_by_user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    for table in ("clinical_form_templates", "clinical_form_responses"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(sa.text(f"CREATE POLICY {table}_tenant_policy ON {table} USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)"))
    op.execute("CREATE INDEX ix_clinical_form_templates_specialty ON clinical_form_templates (clinic_id, specialty_id, status, name)")
    op.execute("CREATE INDEX ix_clinical_form_responses_patient ON clinical_form_responses (clinic_id, patient_id, created_at DESC)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON clinical_form_templates, clinical_form_responses TO healthcare_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS clinical_form_responses")
    op.execute("DROP TABLE IF EXISTS clinical_form_templates")

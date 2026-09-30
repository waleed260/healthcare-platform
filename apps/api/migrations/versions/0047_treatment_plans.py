"""Add tenant-scoped treatment plans and plan items."""
from alembic import op
import sqlalchemy as sa

revision = "0047_treatment_plans"
down_revision = "0046_blueprint_core_foundations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for code, description in (("clinical.read", "Read treatment plans"), ("clinical.manage", "Manage treatment plans")):
        op.execute(sa.text("INSERT INTO permissions (code, description) VALUES (:code, :description) ON CONFLICT (code) DO NOTHING").bindparams(code=code, description=description))
    for role, codes in {"owner": ("clinical.read", "clinical.manage"), "manager": ("clinical.read", "clinical.manage"), "doctor": ("clinical.read", "clinical.manage"), "receptionist": ("clinical.read",)}.items():
        for code in codes:
            op.execute(sa.text("""
                INSERT INTO role_permissions (role_id, permission_code)
                SELECT r.id, :code FROM roles r WHERE r.name = :role ON CONFLICT DO NOTHING
            """).bindparams(role=role, code=code))
    op.execute("""
        CREATE TABLE treatment_plans (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            patient_id uuid NOT NULL,
            created_by_user_id uuid NOT NULL,
            title text NOT NULL,
            diagnosis text NULL,
            status text NOT NULL DEFAULT 'draft',
            starts_on date NULL,
            ends_on date NULL,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            CONSTRAINT uq_treatment_plans_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_treatment_plans_status CHECK (status IN ('draft', 'active', 'completed', 'cancelled')),
            CONSTRAINT ck_treatment_plans_dates CHECK (ends_on IS NULL OR starts_on IS NULL OR starts_on <= ends_on),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES patients (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, created_by_user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE TABLE treatment_plan_items (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            plan_id uuid NOT NULL,
            service_id uuid NULL,
            appointment_id uuid NULL,
            assigned_doctor_id uuid NULL,
            title text NOT NULL,
            instructions text NULL,
            status text NOT NULL DEFAULT 'planned',
            sort_order integer NOT NULL DEFAULT 0,
            due_on date NULL,
            completed_at timestamptz NULL,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_treatment_plan_items_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_treatment_plan_items_status CHECK (status IN ('planned', 'in_progress', 'completed', 'skipped')),
            FOREIGN KEY (clinic_id, plan_id) REFERENCES treatment_plans (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, service_id) REFERENCES services (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, appointment_id) REFERENCES appointments (clinic_id, id) ON DELETE SET NULL,
            FOREIGN KEY (clinic_id, assigned_doctor_id) REFERENCES doctor_profiles (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    for table in ("treatment_plans", "treatment_plan_items"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(sa.text(f"CREATE POLICY {table}_tenant_policy ON {table} USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)"))
    op.execute("CREATE INDEX ix_treatment_plans_patient ON treatment_plans (clinic_id, patient_id, archived_at, updated_at DESC)")
    op.execute("CREATE INDEX ix_treatment_plan_items_plan ON treatment_plan_items (clinic_id, plan_id, sort_order, created_at)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON treatment_plans, treatment_plan_items TO healthcare_runtime")


def downgrade() -> None:
    op.drop_index("ix_treatment_plan_items_plan", table_name="treatment_plan_items")
    op.drop_index("ix_treatment_plans_patient", table_name="treatment_plans")
    op.execute("DROP TABLE IF EXISTS treatment_plan_items")
    op.execute("DROP TABLE IF EXISTS treatment_plans")

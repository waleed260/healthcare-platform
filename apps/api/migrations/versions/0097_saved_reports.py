"""Saved reports: persisted, clinic-scoped report definitions for the report builder.

Config is a validated, allow-listed shape (source/metrics/dimensions/filters/range) — the
run engine only ever emits SQL from a server-side registry, never from these stored fields.
"""
from alembic import op
import sqlalchemy as sa

revision = "0097_saved_reports"
down_revision = "0096_packages_lifecycle_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("INSERT INTO permissions (code, description) VALUES ('report.manage', 'Create and manage saved reports') ON CONFLICT (code) DO NOTHING"))
    for role in ("owner", "manager"):
        op.execute(sa.text("INSERT INTO role_permissions (role_id, permission_code) SELECT r.id, 'report.manage' FROM roles r WHERE r.name = :role ON CONFLICT DO NOTHING").bindparams(role=role))
    op.execute("""
        CREATE TABLE saved_reports (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            name text NOT NULL,
            description text NULL,
            source text NOT NULL,
            config jsonb NOT NULL,
            status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
            created_by_user_id uuid NULL,
            last_run_at timestamptz NULL,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_saved_reports_clinic_id UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id) REFERENCES clinics (id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, created_by_user_id) REFERENCES users (clinic_id, id) ON DELETE SET NULL
        )
    """)
    op.execute("ALTER TABLE saved_reports ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE saved_reports FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY saved_reports_tenant_policy ON saved_reports "
               "USING (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid) "
               "WITH CHECK (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid)")
    op.execute("CREATE INDEX ix_saved_reports_clinic_status ON saved_reports (clinic_id, status, name)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON saved_reports TO healthcare_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS saved_reports")
    op.execute("DELETE FROM role_permissions WHERE permission_code = 'report.manage'")
    op.execute("DELETE FROM permissions WHERE code = 'report.manage'")

"""Create the Phase 2 tenant foundation and RLS probe."""
from alembic import op

revision = "0001_tenant_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("""
        CREATE TABLE clinics (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            name text NOT NULL,
            slug text NOT NULL UNIQUE,
            status text NOT NULL DEFAULT 'active',
            timezone text NOT NULL DEFAULT 'UTC',
            locale text NOT NULL DEFAULT 'en',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            version integer NOT NULL DEFAULT 1
        )
    """)
    op.execute("""
        CREATE TABLE tenant_probe_records (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE RESTRICT,
            label text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            version integer NOT NULL DEFAULT 1,
            CONSTRAINT uq_tenant_probe_records_clinic_id UNIQUE (clinic_id, id)
        )
    """)
    op.execute("ALTER TABLE tenant_probe_records ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant_probe_records FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_probe_records_tenant_policy
        ON tenant_probe_records
        USING (clinic_id = current_setting('app.clinic_id', true)::uuid)
        WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)
    """)
    op.execute("CREATE INDEX ix_tenant_probe_records_clinic_id ON tenant_probe_records (clinic_id)")
    op.execute("GRANT USAGE ON SCHEMA public TO healthcare_runtime")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON clinics, tenant_probe_records TO healthcare_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_probe_records")
    op.execute("DROP TABLE IF EXISTS clinics")

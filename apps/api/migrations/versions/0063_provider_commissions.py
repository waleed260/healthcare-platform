"""Link invoice lines to providers and add per-provider commission rules."""
from alembic import op

revision = "0063_provider_commissions"
down_revision = "0062_clinic_default_currency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE invoice_lines ADD COLUMN provider_id uuid NULL")
    op.execute("ALTER TABLE invoice_lines ADD CONSTRAINT fk_invoice_lines_provider FOREIGN KEY (clinic_id, provider_id) REFERENCES doctor_profiles (clinic_id, id) ON DELETE SET NULL (provider_id)")
    op.execute("CREATE INDEX ix_invoice_lines_provider ON invoice_lines (clinic_id, provider_id) WHERE provider_id IS NOT NULL")
    op.execute("""
        CREATE TABLE provider_commission_rules (
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            doctor_id uuid NOT NULL,
            percent_bp integer NOT NULL CHECK (percent_bp BETWEEN 0 AND 10000),
            active boolean NOT NULL DEFAULT true,
            updated_by uuid NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (clinic_id, doctor_id),
            FOREIGN KEY (clinic_id, doctor_id) REFERENCES doctor_profiles (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("ALTER TABLE provider_commission_rules ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE provider_commission_rules FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY provider_commission_rules_tenant_policy ON provider_commission_rules USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON provider_commission_rules TO healthcare_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS provider_commission_rules")
    op.execute("DROP INDEX IF EXISTS ix_invoice_lines_provider")
    op.execute("ALTER TABLE invoice_lines DROP CONSTRAINT IF EXISTS fk_invoice_lines_provider")
    op.execute("ALTER TABLE invoice_lines DROP COLUMN IF EXISTS provider_id")

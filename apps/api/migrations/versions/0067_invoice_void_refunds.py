"""Add invoice void columns and refunds table for billing phase 5."""
from alembic import op
import sqlalchemy as sa

revision = "0067_invoice_void_refunds"
down_revision = "0066_clinical_tool_states"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE invoices ADD COLUMN void_reason text NULL")
    op.execute("ALTER TABLE invoices ADD COLUMN voided_at timestamptz NULL")
    op.execute("ALTER TABLE invoices ADD COLUMN voided_by_user_id uuid NULL")
    op.execute("ALTER TABLE invoices DROP CONSTRAINT ck_invoices_status")
    op.execute("ALTER TABLE invoices ADD CONSTRAINT ck_invoices_status CHECK (status IN ('unpaid', 'partially_paid', 'paid', 'refunded', 'partially_refunded', 'void'))")
    op.execute("""
        CREATE TABLE refunds (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            invoice_id uuid NOT NULL,
            amount_minor bigint NOT NULL,
            currency char(3) NOT NULL,
            reason text NOT NULL,
            method text NOT NULL,
            reference text NULL,
            refunded_by_user_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_refunds_clinic_id UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, invoice_id) REFERENCES invoices (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, refunded_by_user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT,
            CONSTRAINT ck_refunds_amount CHECK (amount_minor > 0)
        )
    """)
    op.execute("CREATE INDEX ix_refunds_clinic_invoice ON refunds (clinic_id, invoice_id, created_at DESC)")
    op.execute("ALTER TABLE refunds ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE refunds FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY refunds_tenant_policy ON refunds
        USING (clinic_id = current_setting('app.clinic_id', true)::uuid)
        WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)
    """)
    op.execute("GRANT SELECT, INSERT ON refunds TO healthcare_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS refunds")
    op.execute("ALTER TABLE invoices DROP CONSTRAINT IF EXISTS ck_invoices_status")
    op.execute("ALTER TABLE invoices ADD CONSTRAINT ck_invoices_status CHECK (status IN ('unpaid', 'partially_paid', 'paid', 'refunded', 'void'))")
    op.execute("ALTER TABLE invoices DROP COLUMN IF EXISTS voided_by_user_id")
    op.execute("ALTER TABLE invoices DROP COLUMN IF EXISTS voided_at")
    op.execute("ALTER TABLE invoices DROP COLUMN IF EXISTS void_reason")

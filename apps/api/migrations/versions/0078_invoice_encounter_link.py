"""Link invoices to encounter_forms for one-click invoice generation from encounters."""
from alembic import op

revision = "0078_invoice_encounter_link"
down_revision = "0077_invitation_rls_allow_consume"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE invoices
        ADD COLUMN encounter_id uuid NULL,
        ADD CONSTRAINT fk_invoices_encounter
            FOREIGN KEY (clinic_id, encounter_id)
            REFERENCES encounter_forms (clinic_id, id) ON DELETE RESTRICT
    """)
    op.execute("CREATE INDEX ix_invoices_encounter ON invoices (clinic_id, encounter_id) WHERE encounter_id IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_invoices_encounter")
    op.execute("ALTER TABLE invoices DROP CONSTRAINT IF EXISTS fk_invoices_encounter")
    op.execute("ALTER TABLE invoices DROP COLUMN IF EXISTS encounter_id")

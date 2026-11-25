"""Link appointments to leads (one-to-many) so a lead's whole appointment history is durable.

Adds ``appointments.lead_id`` (nullable, tenant-safe composite FK to leads). This is the single
source of truth for the lead<->appointment relationship; the legacy one-to-one scalar
``leads.appointment_id`` is backfilled onto it here and retired in a later cleanup migration once
all readers use the new column. ``ON DELETE SET NULL`` keeps an appointment valid if its lead is
removed. Additive and reversible.
"""
from alembic import op

revision = "0099_appointments_lead_id"
down_revision = "0098_access_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE appointments ADD COLUMN lead_id uuid NULL")
    op.execute("""
        ALTER TABLE appointments ADD CONSTRAINT fk_appointments_lead
        FOREIGN KEY (clinic_id, lead_id) REFERENCES leads (clinic_id, id) ON DELETE SET NULL
    """)
    op.execute(
        "CREATE INDEX ix_appointments_clinic_lead ON appointments (clinic_id, lead_id) "
        "WHERE lead_id IS NOT NULL"
    )
    # Backfill the one-to-many link from the legacy scalar pointer (one-to-one) so historical
    # lead<->appointment associations survive. Runs as migrator (bypasses RLS).
    op.execute("""
        UPDATE appointments a SET lead_id = l.id
        FROM leads l
        WHERE l.appointment_id = a.id AND l.clinic_id = a.clinic_id AND a.lead_id IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_appointments_clinic_lead")
    op.execute("ALTER TABLE appointments DROP CONSTRAINT IF EXISTS fk_appointments_lead")
    op.execute("ALTER TABLE appointments DROP COLUMN IF EXISTS lead_id")

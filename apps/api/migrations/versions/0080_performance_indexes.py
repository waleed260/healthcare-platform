"""Add indexes for high-traffic query paths identified via EXPLAIN ANALYZE profiling."""
from alembic import op

revision = "0080_performance_indexes"
down_revision = "0079_service_materials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_appointments_clinic_status ON appointments (clinic_id, archived_at, status, starts_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_appointments_clinic_branch ON appointments (clinic_id, branch_id, archived_at, starts_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_payments_clinic_paid ON payments (clinic_id, paid_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_invoices_clinic_issued ON invoices (clinic_id, issued_at, status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_payment_allocations_invoice ON payment_allocations (clinic_id, invoice_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_invoice_lines_invoice ON invoice_lines (clinic_id, invoice_id, provider_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_queue_entries_ordering ON queue_entries (clinic_id, status, priority DESC, checked_in_at, id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_queue_entries_ordering")
    op.execute("DROP INDEX IF EXISTS ix_invoice_lines_invoice")
    op.execute("DROP INDEX IF EXISTS ix_payment_allocations_invoice")
    op.execute("DROP INDEX IF EXISTS ix_invoices_clinic_issued")
    op.execute("DROP INDEX IF EXISTS ix_payments_clinic_paid")
    op.execute("DROP INDEX IF EXISTS ix_appointments_clinic_branch")
    op.execute("DROP INDEX IF EXISTS ix_appointments_clinic_status")

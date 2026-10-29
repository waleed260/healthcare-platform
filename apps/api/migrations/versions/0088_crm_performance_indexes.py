"""Add indexes for CRM tab-switching and scalability bottlenecks."""
from alembic import op

revision = "0088_crm_performance_indexes"
down_revision = "0087_add_warehouse_id_to_inventory_stock"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # Patient list cursor keyset (ORDER BY full_name, id)
    op.execute("CREATE INDEX IF NOT EXISTS ix_patients_clinic_name ON patients (clinic_id, full_name, id) WHERE archived_at IS NULL AND duplicate_of IS NULL")
    # Patient ILIKE search on full_name
    op.execute("CREATE INDEX IF NOT EXISTS ix_patients_clinic_name_trgm ON patients USING gin (full_name gin_trgm_ops) WHERE archived_at IS NULL AND duplicate_of IS NULL")
    # Appointments date-range queries (schedule page)
    op.execute("CREATE INDEX IF NOT EXISTS ix_appointments_clinic_starts ON appointments (clinic_id, starts_at, id) WHERE archived_at IS NULL")
    # Follow-up tasks due query (dashboard summary)
    op.execute("CREATE INDEX IF NOT EXISTS ix_followup_tasks_due ON follow_up_tasks (clinic_id, status, due_at) WHERE status IN ('due', 'contacted', 'booked')")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_followup_tasks_due")
    op.execute("DROP INDEX IF EXISTS ix_appointments_clinic_starts")
    op.execute("DROP INDEX IF EXISTS ix_patients_clinic_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_patients_clinic_name")

"""Integrity guards found by the quality review.

- One active encounter per appointment and one non-void invoice per encounter
  (route checks were check-then-insert races).
- Indexes on hot tenant lookups that only had the clinic-wide composite.
- The runtime role loses UPDATE/DELETE on append-only and financial ledger
  tables the application never edits in place.
- export_jobs gets a real expiry for the 60-second download token.
"""
from alembic import op


revision = "0094_integrity_guards"
down_revision = "0093_leads_branch_id"
branch_labels = None
depends_on = None

_INDEXES = {
    "ix_appointments_clinic_patient": "appointments (clinic_id, patient_id)",
    "ix_appointments_clinic_doctor_starts": "appointments (clinic_id, doctor_id, starts_at)",
    "ix_appointment_history_clinic_appointment": "appointment_history (clinic_id, appointment_id)",
    "ix_follow_up_tasks_clinic_patient": "follow_up_tasks (clinic_id, patient_id)",
    "ix_follow_up_tasks_clinic_appointment": "follow_up_tasks (clinic_id, appointment_id)",
    "ix_inventory_stock_clinic_product": "inventory_stock (clinic_id, product_id)",
    "ix_user_roles_role": "user_roles (role_id)",
}
_NO_DELETE = ("appointment_history", "patient_merge_events", "payments", "payment_allocations", "invoice_lines", "inventory_adjustments")
_NO_UPDATE = ("appointment_history", "patient_merge_events", "payments", "payment_allocations", "inventory_adjustments")


def upgrade() -> None:
    # If either index fails on existing duplicates, resolve them (archive the extra
    # encounter / void the extra invoice) before re-running; nothing is dropped here.
    op.execute("CREATE UNIQUE INDEX uq_encounter_forms_active_appointment ON encounter_forms (clinic_id, appointment_id) WHERE appointment_id IS NOT NULL AND archived_at IS NULL")
    op.execute("CREATE UNIQUE INDEX uq_invoices_active_encounter ON invoices (clinic_id, encounter_id) WHERE encounter_id IS NOT NULL AND status <> 'void'")
    for name, target in _INDEXES.items():
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {target}")
    op.execute(f"REVOKE DELETE ON {', '.join(_NO_DELETE)} FROM healthcare_runtime")
    op.execute(f"REVOKE UPDATE ON {', '.join(_NO_UPDATE)} FROM healthcare_runtime")
    op.execute("ALTER TABLE export_jobs ADD COLUMN download_token_expires_at timestamptz NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE export_jobs DROP COLUMN download_token_expires_at")
    op.execute(f"GRANT UPDATE ON {', '.join(_NO_UPDATE)} TO healthcare_runtime")
    op.execute(f"GRANT DELETE ON {', '.join(_NO_DELETE)} TO healthcare_runtime")
    for name in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
    op.execute("DROP INDEX IF EXISTS uq_invoices_active_encounter")
    op.execute("DROP INDEX IF EXISTS uq_encounter_forms_active_appointment")

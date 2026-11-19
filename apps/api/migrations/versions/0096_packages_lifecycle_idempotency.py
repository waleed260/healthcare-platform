"""Packages lifecycle + duplicate-sale protection.

- package_definitions gains an 'inactive' status so a package can be deactivated
  (not sellable, reversible) distinctly from 'archived' (soft-deleted/hidden).
- patient_packages gains an optional idempotency_key with a per-clinic partial
  unique index, so a repeated "sell package" request cannot create duplicate
  purchases + session ledgers.
"""
from alembic import op


revision = "0096_packages_lifecycle_idempotency"
down_revision = "0095_roles_tenant_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE package_definitions DROP CONSTRAINT IF EXISTS package_definitions_status_check")
    op.execute("ALTER TABLE package_definitions ADD CONSTRAINT package_definitions_status_check "
               "CHECK (status IN ('active', 'inactive', 'archived'))")
    op.execute("ALTER TABLE patient_packages ADD COLUMN idempotency_key uuid NULL")
    op.execute("CREATE UNIQUE INDEX uq_patient_packages_idempotency "
               "ON patient_packages (clinic_id, idempotency_key) WHERE idempotency_key IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_patient_packages_idempotency")
    op.execute("ALTER TABLE patient_packages DROP COLUMN IF EXISTS idempotency_key")
    op.execute("ALTER TABLE package_definitions DROP CONSTRAINT IF EXISTS package_definitions_status_check")
    op.execute("ALTER TABLE package_definitions ADD CONSTRAINT package_definitions_status_check "
               "CHECK (status IN ('active', 'archived'))")

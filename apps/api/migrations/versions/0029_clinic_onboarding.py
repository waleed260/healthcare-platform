"""Persist clinic onboarding completion without changing operational status."""
from alembic import op


revision = "0029_clinic_onboarding"
down_revision = "0028_catalog_resource_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE clinics ADD COLUMN onboarding_completed_at timestamptz NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE clinics DROP COLUMN IF EXISTS onboarding_completed_at")

"""Add a clinic default currency chosen during first-login setup."""
from alembic import op

revision = "0062_clinic_default_currency"
down_revision = "0061_website_content"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE clinics ADD COLUMN default_currency char(3) NOT NULL DEFAULT 'PKR' CONSTRAINT ck_clinics_currency CHECK (default_currency ~ '^[A-Z]{3}$')")


def downgrade() -> None:
    op.execute("ALTER TABLE clinics DROP COLUMN IF EXISTS default_currency")

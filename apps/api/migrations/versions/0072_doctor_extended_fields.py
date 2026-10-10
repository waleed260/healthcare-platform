"""Add extended fields to doctor_profiles for enhanced doctor management."""
from alembic import op

revision = "0072_doctor_extended_fields"
down_revision = "0071_internal_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE doctor_profiles ADD COLUMN license_number text NULL")
    op.execute("ALTER TABLE doctor_profiles ADD COLUMN phone text NULL")
    op.execute("ALTER TABLE doctor_profiles ADD COLUMN email text NULL")
    op.execute("ALTER TABLE doctor_profiles ADD COLUMN booking_status text NOT NULL DEFAULT 'accepting'")
    op.execute("ALTER TABLE doctor_profiles ADD CONSTRAINT ck_doctor_booking_status CHECK (booking_status IN ('accepting', 'paused', 'not_accepting'))")
    op.execute("ALTER TABLE doctor_profiles ADD COLUMN room_id uuid NULL")
    op.execute("ALTER TABLE doctor_profiles ADD COLUMN notes text NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE doctor_profiles DROP CONSTRAINT IF EXISTS ck_doctor_booking_status")
    op.execute("ALTER TABLE doctor_profiles DROP COLUMN IF EXISTS notes")
    op.execute("ALTER TABLE doctor_profiles DROP COLUMN IF EXISTS room_id")
    op.execute("ALTER TABLE doctor_profiles DROP COLUMN IF EXISTS booking_status")
    op.execute("ALTER TABLE doctor_profiles DROP COLUMN IF EXISTS email")
    op.execute("ALTER TABLE doctor_profiles DROP COLUMN IF EXISTS phone")
    op.execute("ALTER TABLE doctor_profiles DROP COLUMN IF EXISTS license_number")

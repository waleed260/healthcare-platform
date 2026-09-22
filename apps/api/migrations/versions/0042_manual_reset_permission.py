"""Add the owner-only manual staff password reset permission."""

from alembic import op
import sqlalchemy as sa


revision = "0042_manual_reset_permission"
down_revision = "0041_encrypt_document_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        INSERT INTO permissions (code, description)
        VALUES ('staff.password_reset', 'Issue manual password reset links for staff')
        ON CONFLICT (code) DO NOTHING
    """))
    op.execute(sa.text("""
        INSERT INTO role_permissions (role_id, permission_code)
        SELECT id, 'staff.password_reset'
        FROM roles
        WHERE clinic_id IS NULL AND name = 'owner'
        ON CONFLICT DO NOTHING
    """))


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM role_permissions WHERE permission_code = 'staff.password_reset'"))
    op.execute(sa.text("DELETE FROM permissions WHERE code = 'staff.password_reset'"))

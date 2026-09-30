"""Add the clinic reporting read permission."""
from alembic import op
import sqlalchemy as sa

revision = "0049_reporting_permission"
down_revision = "0048_master_service_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("INSERT INTO permissions (code, description) VALUES ('report.read', 'Read clinic operational reports') ON CONFLICT (code) DO NOTHING"))
    for role in ("owner", "manager", "doctor", "receptionist"):
        op.execute(sa.text("""
            INSERT INTO role_permissions (role_id, permission_code)
            SELECT r.id, 'report.read' FROM roles r WHERE r.name = :role ON CONFLICT DO NOTHING
        """).bindparams(role=role))


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM role_permissions WHERE permission_code = 'report.read'"))
    op.execute(sa.text("DELETE FROM permissions WHERE code = 'report.read'"))

"""Complete the canonical permission catalog in PostgreSQL."""
from alembic import op
import sqlalchemy as sa

revision = "0017_permission_catalog"
down_revision = "0016_public_booking_management"
branch_labels = None
depends_on = None


CATALOG = {
    "branch.read": "Read branches",
    "branch.manage": "Manage branches",
    "admin.clinic.manage": "Manage clinic lifecycle",
    "admin.plan.manage": "Manage plans and limits",
    "admin.support.access": "Create audited support sessions",
    "admin.analytics.read": "Read platform analytics",
}


def upgrade() -> None:
    for code, description in CATALOG.items():
        op.execute(sa.text("INSERT INTO permissions (code, description) VALUES (:code, :description) ON CONFLICT (code) DO NOTHING").bindparams(code=code, description=description))
    for role in ("owner", "manager"):
        for code in ("branch.read", "branch.manage"):
            op.execute(sa.text("INSERT INTO role_permissions (role_id, permission_code) SELECT r.id, :code FROM roles r WHERE r.name = :role ON CONFLICT DO NOTHING").bindparams(role=role, code=code))


def downgrade() -> None:
    for code in CATALOG:
        op.execute(sa.text("DELETE FROM role_permissions WHERE permission_code = :code").bindparams(code=code))
        op.execute(sa.text("DELETE FROM permissions WHERE code = :code").bindparams(code=code))

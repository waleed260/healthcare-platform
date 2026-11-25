"""Add a dedicated lead.convert permission so formal conversion is separately authorised.

Conversion turns a lead into a patient record and is terminal for the sales pipeline, so it is
no longer covered by the broad lead.manage grant. Granted to owner and manager, mirroring the
report.manage precedent. The permission is also registered in
``app.modules.authorization.permissions.PERMISSIONS`` (require_permission validates against it).
"""
from alembic import op
import sqlalchemy as sa

revision = "0101_lead_convert_permission"
down_revision = "0100_lead_stage_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "INSERT INTO permissions (code, description) VALUES "
        "('lead.convert', 'Formally convert a lead into a patient') ON CONFLICT (code) DO NOTHING"
    ))
    for role in ("owner", "manager"):
        op.execute(sa.text(
            "INSERT INTO role_permissions (role_id, permission_code) "
            "SELECT r.id, 'lead.convert' FROM roles r WHERE r.name = :role ON CONFLICT DO NOTHING"
        ).bindparams(role=role))


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission_code = 'lead.convert'")
    op.execute("DELETE FROM permissions WHERE code = 'lead.convert'")

"""Grant supplier/purchase/warehouse/transfer permissions to all roles that have inventory permissions."""
from alembic import op
import sqlalchemy as sa

revision = "0083_grant_inventory_permissions_to_all_roles"
down_revision = "0082_suppliers_warehouses_transfers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Grant .manage permissions to all roles that have inventory.manage
    manage_perms = ["supplier.manage", "purchase.manage", "warehouse.manage", "transfer.manage"]
    for code in manage_perms:
        op.execute(sa.text(
            "INSERT INTO role_permissions (role_id, permission_code) "
            "SELECT rp.role_id, :code FROM role_permissions rp "
            "WHERE rp.permission_code = 'inventory.manage' "
            "ON CONFLICT DO NOTHING"
        ).bindparams(code=code))

    # Grant .read permissions to all roles that have inventory.read
    read_perms = ["supplier.read", "purchase.read", "warehouse.read", "transfer.read"]
    for code in read_perms:
        op.execute(sa.text(
            "INSERT INTO role_permissions (role_id, permission_code) "
            "SELECT rp.role_id, :code FROM role_permissions rp "
            "WHERE rp.permission_code = 'inventory.read' "
            "ON CONFLICT DO NOTHING"
        ).bindparams(code=code))

    # Also grant .read to roles that have inventory.manage (manage implies read)
    for code in read_perms:
        op.execute(sa.text(
            "INSERT INTO role_permissions (role_id, permission_code) "
            "SELECT rp.role_id, :code FROM role_permissions rp "
            "WHERE rp.permission_code = 'inventory.manage' "
            "ON CONFLICT DO NOTHING"
        ).bindparams(code=code))


def downgrade() -> None:
    pass

"""add warehouse_id to inventory_stock for per-warehouse stock tracking

Revision ID: 0087_add_warehouse_id_to_inventory_stock
Revises: 0086_fix_rls_policy_parameter
"""

revision = "0087_add_warehouse_id_to_inventory_stock"
down_revision = "0086_fix_rls_policy_parameter"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.execute("ALTER TABLE inventory_stock ADD COLUMN warehouse_id uuid")
    op.execute("""
        ALTER TABLE inventory_stock
        ADD CONSTRAINT fk_inventory_stock_warehouse
        FOREIGN KEY (clinic_id, warehouse_id) REFERENCES warehouses (clinic_id, id) ON DELETE SET NULL
    """)
    op.execute("CREATE INDEX ix_inventory_stock_warehouse ON inventory_stock (clinic_id, warehouse_id) WHERE warehouse_id IS NOT NULL")
    op.execute("""
        DROP INDEX IF EXISTS ix_inventory_stock_low;
        CREATE INDEX ix_inventory_stock_low ON inventory_stock (clinic_id, branch_id, warehouse_id, product_id, quantity)
    """)
    op.execute("ALTER TABLE inventory_adjustments ADD COLUMN warehouse_id uuid")
    op.execute("""
        ALTER TABLE inventory_adjustments
        ADD CONSTRAINT fk_inventory_adjustments_warehouse
        FOREIGN KEY (clinic_id, warehouse_id) REFERENCES warehouses (clinic_id, id) ON DELETE SET NULL
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE inventory_adjustments DROP CONSTRAINT IF EXISTS fk_inventory_adjustments_warehouse")
    op.execute("ALTER TABLE inventory_adjustments DROP COLUMN IF EXISTS warehouse_id")
    op.execute("DROP INDEX IF EXISTS ix_inventory_stock_warehouse")
    op.execute("ALTER TABLE inventory_stock DROP CONSTRAINT IF EXISTS fk_inventory_stock_warehouse")
    op.execute("ALTER TABLE inventory_stock DROP COLUMN IF EXISTS warehouse_id")
    op.execute("""
        DROP INDEX IF EXISTS ix_inventory_stock_low;
        CREATE INDEX ix_inventory_stock_low ON inventory_stock (clinic_id, branch_id, product_id, quantity)
    """)

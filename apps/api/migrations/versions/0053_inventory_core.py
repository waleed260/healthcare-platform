"""Add clinic inventory products, branch stock, and audited adjustments."""
from alembic import op
import sqlalchemy as sa

revision = "0053_inventory_core"
down_revision = "0052_public_lead_intake"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for code, description in (("inventory.read", "Read clinic inventory"), ("inventory.manage", "Manage clinic inventory and adjustments")):
        op.execute(sa.text("INSERT INTO permissions (code, description) VALUES (:code, :description) ON CONFLICT (code) DO NOTHING").bindparams(code=code, description=description))
    roles = {"owner": ("inventory.read", "inventory.manage"), "manager": ("inventory.read", "inventory.manage"), "doctor": ("inventory.read",), "receptionist": ("inventory.read", "inventory.manage")}
    for role, codes in roles.items():
        for code in codes:
            op.execute(sa.text("INSERT INTO role_permissions (role_id, permission_code) SELECT r.id, :code FROM roles r WHERE r.name = :role ON CONFLICT DO NOTHING").bindparams(role=role, code=code))
    op.execute("""
        CREATE TABLE inventory_products (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            sku text NULL,
            name text NOT NULL,
            product_type text NOT NULL,
            unit text NOT NULL DEFAULT 'unit',
            minimum_stock numeric(12,3) NOT NULL DEFAULT 0 CHECK (minimum_stock >= 0),
            status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            CONSTRAINT uq_inventory_products_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT uq_inventory_products_sku UNIQUE (clinic_id, sku),
            CONSTRAINT ck_inventory_products_type CHECK (product_type IN ('product', 'medicine', 'consumable', 'material')),
            FOREIGN KEY (clinic_id) REFERENCES clinics (id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE inventory_stock (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            branch_id uuid NOT NULL,
            product_id uuid NOT NULL,
            quantity numeric(12,3) NOT NULL DEFAULT 0 CHECK (quantity >= 0),
            version integer NOT NULL DEFAULT 1,
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_inventory_stock_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT uq_inventory_stock_branch_product UNIQUE (clinic_id, branch_id, product_id),
            FOREIGN KEY (clinic_id, branch_id) REFERENCES branches (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, product_id) REFERENCES inventory_products (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE inventory_adjustments (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            branch_id uuid NOT NULL,
            product_id uuid NOT NULL,
            delta numeric(12,3) NOT NULL CHECK (delta <> 0),
            reason text NOT NULL,
            adjusted_by_user_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_inventory_adjustments_clinic_id UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, branch_id) REFERENCES branches (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, product_id) REFERENCES inventory_products (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, adjusted_by_user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    for table in ("inventory_products", "inventory_stock", "inventory_adjustments"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(sa.text(f"CREATE POLICY {table}_tenant_policy ON {table} USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)"))
    op.execute("CREATE INDEX ix_inventory_stock_low ON inventory_stock (clinic_id, branch_id, product_id, quantity)")
    op.execute("CREATE INDEX ix_inventory_adjustments_product ON inventory_adjustments (clinic_id, product_id, branch_id, created_at DESC)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON inventory_products, inventory_stock, inventory_adjustments TO healthcare_runtime")


def downgrade() -> None:
    for table in ("inventory_adjustments", "inventory_stock", "inventory_products"):
        op.execute(f"DROP TABLE IF EXISTS {table}")

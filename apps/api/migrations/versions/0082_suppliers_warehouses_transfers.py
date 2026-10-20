"""Add suppliers, warehouses, purchase orders, and inventory transfers."""
from alembic import op
import sqlalchemy as sa

revision = "0082_suppliers_warehouses_transfers"
down_revision = "0081_inventory_categories_and_pricing"
branch_labels = None
depends_on = None

_RLS_TEMPLATE = (
    "CREATE POLICY {table}_tenant_policy ON {table} "
    "USING (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid) "
    "WITH CHECK (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid)"
)


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(sa.text(_RLS_TEMPLATE.format(table=table)))
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO healthcare_runtime")


def upgrade() -> None:
    # ── Permissions ──────────────────────────────────────────────────────
    perms = {
        "supplier.read": "View supplier directory",
        "supplier.manage": "Create and edit suppliers",
        "purchase.read": "View purchase orders",
        "purchase.manage": "Create and manage purchase orders",
        "warehouse.read": "View warehouse locations",
        "warehouse.manage": "Create and manage warehouses",
        "transfer.read": "View inventory transfers",
        "transfer.manage": "Create and manage inventory transfers",
    }
    for code, description in perms.items():
        op.execute(sa.text(
            "INSERT INTO permissions (code, description) VALUES (:code, :description) ON CONFLICT (code) DO NOTHING"
        ).bindparams(code=code, description=description))
    roles = {
        "owner": list(perms.keys()),
        "manager": list(perms.keys()),
        "doctor": [c for c in perms if c.endswith(".read")],
        "receptionist": [c for c in perms if c.endswith(".read")],
    }
    for role, codes in roles.items():
        for code in codes:
            op.execute(sa.text(
                "INSERT INTO role_permissions (role_id, permission_code) "
                "SELECT r.id, :code FROM roles r WHERE r.name = :role ON CONFLICT DO NOTHING"
            ).bindparams(role=role, code=code))

    # ── Suppliers ────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE suppliers (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            name text NOT NULL,
            contact_name text NULL,
            email text NULL,
            phone text NULL,
            address jsonb NULL,
            notes text NULL,
            status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            CONSTRAINT uq_suppliers_clinic_id UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id) REFERENCES clinics (id) ON DELETE CASCADE
        )
    """)
    _enable_rls("suppliers")
    op.execute("CREATE INDEX ix_suppliers_clinic_name ON suppliers (clinic_id, name)")

    # ── Warehouses ───────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE warehouses (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            name text NOT NULL,
            code text NOT NULL,
            address jsonb NULL,
            warehouse_type text NOT NULL DEFAULT 'warehouse' CHECK (warehouse_type IN ('warehouse', 'store', 'cold_storage')),
            branch_id uuid NOT NULL,
            contact_name text NULL,
            contact_phone text NULL,
            status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            CONSTRAINT uq_warehouses_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT uq_warehouses_code UNIQUE (clinic_id, code),
            FOREIGN KEY (clinic_id) REFERENCES clinics (id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, branch_id) REFERENCES branches (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    _enable_rls("warehouses")
    op.execute("CREATE INDEX ix_warehouses_clinic_branch ON warehouses (clinic_id, branch_id)")

    # ── PO number sequences ─────────────────────────────────────────────
    op.execute("""
        CREATE TABLE po_number_sequences (
            clinic_id uuid NOT NULL REFERENCES clinics (id) ON DELETE CASCADE,
            next_value bigint NOT NULL DEFAULT 1,
            PRIMARY KEY (clinic_id),
            CONSTRAINT ck_po_sequence_value CHECK (next_value > 0)
        )
    """)
    _enable_rls("po_number_sequences")

    # ── Purchase orders ──────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE purchase_orders (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            order_number text NOT NULL,
            supplier_id uuid NOT NULL,
            warehouse_id uuid NOT NULL,
            status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'ordered', 'partially_received', 'received', 'cancelled')),
            total_minor bigint NULL,
            currency char(3) NOT NULL DEFAULT 'PKR',
            notes text NULL,
            ordered_by_user_id uuid NOT NULL,
            ordered_at timestamptz NULL,
            received_at timestamptz NULL,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_purchase_orders_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT uq_purchase_orders_number UNIQUE (clinic_id, order_number),
            FOREIGN KEY (clinic_id) REFERENCES clinics (id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, supplier_id) REFERENCES suppliers (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, warehouse_id) REFERENCES warehouses (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, ordered_by_user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    _enable_rls("purchase_orders")
    op.execute("CREATE INDEX ix_purchase_orders_status ON purchase_orders (clinic_id, status)")
    op.execute("CREATE INDEX ix_purchase_orders_supplier ON purchase_orders (clinic_id, supplier_id)")

    # ── Purchase order lines ─────────────────────────────────────────────
    op.execute("""
        CREATE TABLE purchase_order_lines (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            purchase_order_id uuid NOT NULL,
            product_id uuid NOT NULL,
            quantity_ordered numeric(12,3) NOT NULL CHECK (quantity_ordered > 0),
            quantity_received numeric(12,3) NOT NULL DEFAULT 0 CHECK (quantity_received >= 0),
            unit_cost_minor bigint NOT NULL CHECK (unit_cost_minor >= 0),
            currency char(3) NOT NULL DEFAULT 'PKR',
            CONSTRAINT uq_po_lines_clinic_id UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id) REFERENCES clinics (id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, purchase_order_id) REFERENCES purchase_orders (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, product_id) REFERENCES inventory_products (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    _enable_rls("purchase_order_lines")
    op.execute("CREATE INDEX ix_po_lines_order ON purchase_order_lines (clinic_id, purchase_order_id)")

    # ── Transfer number sequences ────────────────────────────────────────
    op.execute("""
        CREATE TABLE transfer_number_sequences (
            clinic_id uuid NOT NULL REFERENCES clinics (id) ON DELETE CASCADE,
            next_value bigint NOT NULL DEFAULT 1,
            PRIMARY KEY (clinic_id),
            CONSTRAINT ck_transfer_sequence_value CHECK (next_value > 0)
        )
    """)
    _enable_rls("transfer_number_sequences")

    # ── Inventory transfers ──────────────────────────────────────────────
    op.execute("""
        CREATE TABLE inventory_transfers (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            transfer_number text NOT NULL,
            source_warehouse_id uuid NOT NULL,
            destination_warehouse_id uuid NOT NULL,
            status text NOT NULL DEFAULT 'created' CHECK (status IN ('created', 'handover_for_transit', 'received', 'cancelled')),
            initiated_by_user_id uuid NOT NULL,
            driver_name text NULL,
            driver_phone text NULL,
            handed_over_by_user_id uuid NULL,
            handed_over_at timestamptz NULL,
            received_by_user_id uuid NULL,
            received_at timestamptz NULL,
            cancelled_by_user_id uuid NULL,
            cancelled_at timestamptz NULL,
            cancel_reason text NULL,
            notes text NULL,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_transfers_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT uq_transfers_number UNIQUE (clinic_id, transfer_number),
            CONSTRAINT ck_transfers_different_warehouses CHECK (source_warehouse_id <> destination_warehouse_id),
            FOREIGN KEY (clinic_id) REFERENCES clinics (id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, source_warehouse_id) REFERENCES warehouses (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, destination_warehouse_id) REFERENCES warehouses (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, initiated_by_user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    _enable_rls("inventory_transfers")
    op.execute("CREATE INDEX ix_transfers_status ON inventory_transfers (clinic_id, status)")
    op.execute("CREATE INDEX ix_transfers_source ON inventory_transfers (clinic_id, source_warehouse_id)")
    op.execute("CREATE INDEX ix_transfers_dest ON inventory_transfers (clinic_id, destination_warehouse_id)")

    # ── Inventory transfer lines ─────────────────────────────────────────
    op.execute("""
        CREATE TABLE inventory_transfer_lines (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            transfer_id uuid NOT NULL,
            product_id uuid NOT NULL,
            quantity_sent numeric(12,3) NOT NULL CHECK (quantity_sent > 0),
            quantity_received numeric(12,3) NULL CHECK (quantity_received IS NULL OR quantity_received >= 0),
            condition text NOT NULL DEFAULT 'pending' CHECK (condition IN ('pending', 'good', 'damaged', 'short')),
            checked_by_user_id uuid NULL,
            checked_at timestamptz NULL,
            notes text NULL,
            CONSTRAINT uq_transfer_lines_clinic_id UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id) REFERENCES clinics (id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, transfer_id) REFERENCES inventory_transfers (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, product_id) REFERENCES inventory_products (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    _enable_rls("inventory_transfer_lines")
    op.execute("CREATE INDEX ix_transfer_lines_transfer ON inventory_transfer_lines (clinic_id, transfer_id)")


def downgrade() -> None:
    for table in (
        "inventory_transfer_lines", "inventory_transfers", "transfer_number_sequences",
        "purchase_order_lines", "purchase_orders", "po_number_sequences",
        "warehouses", "suppliers",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    codes = (
        "supplier.read", "supplier.manage", "purchase.read", "purchase.manage",
        "warehouse.read", "warehouse.manage", "transfer.read", "transfer.manage",
    )
    for code in codes:
        op.execute(sa.text("DELETE FROM role_permissions WHERE permission_code = :code").bindparams(code=code))
        op.execute(sa.text("DELETE FROM permissions WHERE code = :code").bindparams(code=code))

"""Add inventory categories table and pricing columns to inventory_products."""
from alembic import op
import sqlalchemy as sa

revision = "0081_inventory_categories_and_pricing"
down_revision = "0080_performance_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE inventory_categories (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            name text NOT NULL,
            slug text NOT NULL,
            display_order integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_inventory_categories_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT uq_inventory_categories_slug UNIQUE (clinic_id, slug),
            FOREIGN KEY (clinic_id) REFERENCES clinics (id) ON DELETE CASCADE
        )
    """)
    op.execute("ALTER TABLE inventory_categories ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE inventory_categories FORCE ROW LEVEL SECURITY")
    op.execute(sa.text(
        "CREATE POLICY inventory_categories_tenant_policy ON inventory_categories "
        "USING (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid) "
        "WITH CHECK (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid)"
    ))
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON inventory_categories TO healthcare_runtime")
    op.execute("CREATE INDEX ix_inventory_categories_order ON inventory_categories (clinic_id, display_order, name)")

    op.execute("ALTER TABLE inventory_products ADD COLUMN category_id uuid NULL REFERENCES inventory_categories (id) ON DELETE SET NULL")
    op.execute("ALTER TABLE inventory_products DROP CONSTRAINT IF EXISTS ck_inventory_products_type")
    op.execute("ALTER TABLE inventory_products ALTER COLUMN product_type DROP NOT NULL")
    op.execute("ALTER TABLE inventory_products ADD COLUMN cost_minor bigint NULL")
    op.execute("ALTER TABLE inventory_products ADD COLUMN selling_price_minor bigint NULL")
    op.execute("ALTER TABLE inventory_products ADD COLUMN currency char(3) NULL DEFAULT 'PKR'")
    op.execute("ALTER TABLE inventory_products ADD COLUMN tax_inclusive boolean NOT NULL DEFAULT false")
    op.execute("CREATE INDEX ix_inventory_products_category ON inventory_products (clinic_id, category_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_inventory_products_category")
    op.execute("ALTER TABLE inventory_products DROP COLUMN IF EXISTS tax_inclusive")
    op.execute("ALTER TABLE inventory_products DROP COLUMN IF EXISTS currency")
    op.execute("ALTER TABLE inventory_products DROP COLUMN IF EXISTS selling_price_minor")
    op.execute("ALTER TABLE inventory_products DROP COLUMN IF EXISTS cost_minor")
    op.execute("ALTER TABLE inventory_products ALTER COLUMN product_type SET NOT NULL")
    op.execute("ALTER TABLE inventory_products ADD CONSTRAINT ck_inventory_products_type CHECK (product_type IN ('product', 'medicine', 'consumable', 'material'))")
    op.execute("ALTER TABLE inventory_products DROP COLUMN IF EXISTS category_id")
    op.execute("DROP INDEX IF EXISTS ix_inventory_categories_order")
    op.execute("DROP TABLE IF EXISTS inventory_categories")

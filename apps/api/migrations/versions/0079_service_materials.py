"""Junction table linking services to inventory products (required materials)."""
from alembic import op
import sqlalchemy as sa

revision = "0079_service_materials"
down_revision = "0078_invoice_encounter_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE service_materials (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            service_id uuid NOT NULL,
            inventory_product_id uuid NOT NULL,
            default_quantity numeric(12,3) NOT NULL DEFAULT 1 CHECK (default_quantity > 0),
            notes text NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_service_materials_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT uq_service_materials_svc_prod UNIQUE (clinic_id, service_id, inventory_product_id),
            FOREIGN KEY (clinic_id, service_id) REFERENCES services (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, inventory_product_id) REFERENCES inventory_products (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("ALTER TABLE service_materials ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE service_materials FORCE ROW LEVEL SECURITY")
    op.execute(sa.text("CREATE POLICY service_materials_tenant_policy ON service_materials USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)"))
    op.execute("CREATE INDEX ix_service_materials_product ON service_materials (clinic_id, inventory_product_id)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON service_materials TO healthcare_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS service_materials")

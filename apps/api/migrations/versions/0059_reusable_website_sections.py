"""Add reusable website sections that can be inserted as independent copies or globally synced."""
from alembic import op

revision = "0059_reusable_website_sections"
down_revision = "0058_finance_and_upgrades"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE reusable_sections (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            name text NOT NULL,
            section_type text NOT NULL,
            layout_key text NOT NULL,
            content jsonb NOT NULL DEFAULT '{}'::jsonb,
            version integer NOT NULL DEFAULT 1,
            created_by uuid NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_reusable_sections_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT uq_reusable_sections_name UNIQUE (clinic_id, name)
        )
    """)
    op.execute("ALTER TABLE website_sections ADD COLUMN reusable_section_id uuid NULL")
    op.execute("ALTER TABLE website_sections ADD CONSTRAINT fk_website_sections_reusable FOREIGN KEY (clinic_id, reusable_section_id) REFERENCES reusable_sections (clinic_id, id) ON DELETE SET NULL (reusable_section_id)")
    op.execute("CREATE INDEX ix_website_sections_reusable ON website_sections (clinic_id, reusable_section_id) WHERE reusable_section_id IS NOT NULL")
    op.execute("ALTER TABLE reusable_sections ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE reusable_sections FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY reusable_sections_tenant_policy ON reusable_sections USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON reusable_sections TO healthcare_runtime")


def downgrade() -> None:
    op.execute("ALTER TABLE website_sections DROP CONSTRAINT IF EXISTS fk_website_sections_reusable")
    op.execute("DROP INDEX IF EXISTS ix_website_sections_reusable")
    op.execute("ALTER TABLE website_sections DROP COLUMN IF EXISTS reusable_section_id")
    op.execute("DROP TABLE IF EXISTS reusable_sections")

"""Create theme_instances table for multi-theme draft/live isolation."""
from alembic import op
import sqlalchemy as sa

revision = "0022_theme_instances"
down_revision = "0021_expand_section_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE theme_instances (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            website_id uuid NOT NULL,
            name text NOT NULL DEFAULT 'Default',
            status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'live', 'archived')),
            brand_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_by uuid NULL,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            CONSTRAINT uq_theme_instances_clinic_id UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, website_id) REFERENCES websites (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("ALTER TABLE theme_instances ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE theme_instances FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY theme_instances_tenant_policy ON theme_instances
        USING (clinic_id = current_setting('app.clinic_id', true)::uuid)
        WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON theme_instances TO healthcare_runtime")

    op.execute("ALTER TABLE website_pages ADD COLUMN theme_instance_id uuid NULL")
    op.execute("""
        ALTER TABLE website_pages
        ADD CONSTRAINT fk_website_pages_theme_instance
        FOREIGN KEY (clinic_id, theme_instance_id)
        REFERENCES theme_instances (clinic_id, id)
        ON DELETE SET NULL
    """)

    op.execute("""
        INSERT INTO theme_instances (clinic_id, website_id, name, status, brand_snapshot)
        SELECT w.clinic_id, w.id, 'Live', 'live', COALESCE(w.brand, '{}'::jsonb)
        FROM websites w
        WHERE w.archived_at IS NULL
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE website_pages DROP CONSTRAINT IF EXISTS fk_website_pages_theme_instance")
    op.execute("ALTER TABLE website_pages DROP COLUMN IF EXISTS theme_instance_id")
    op.execute("DROP TABLE IF EXISTS theme_instances")

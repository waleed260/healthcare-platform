"""Harden immutable website snapshots for publish and rollback commands."""
from alembic import op

revision = "0015_website_publishing"
down_revision = "0014_appointment_commands"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION prevent_website_snapshot_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.snapshot IS DISTINCT FROM OLD.snapshot OR NEW.checksum IS DISTINCT FROM OLD.checksum OR NEW.website_id IS DISTINCT FROM OLD.website_id OR NEW.version_number IS DISTINCT FROM OLD.version_number THEN
                RAISE EXCEPTION 'website snapshots are immutable';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("CREATE TRIGGER website_versions_immutable BEFORE UPDATE ON website_versions FOR EACH ROW EXECUTE FUNCTION prevent_website_snapshot_mutation()")
    op.execute("CREATE POLICY domain_verifications_public_read ON domain_verifications FOR SELECT USING (observed_status = 'verified')")
    op.execute("CREATE INDEX ix_domain_verifications_host_status ON domain_verifications (hostname, observed_status)")


def downgrade() -> None:
    op.drop_index("ix_domain_verifications_host_status", table_name="domain_verifications")
    op.execute("DROP POLICY IF EXISTS domain_verifications_public_read ON domain_verifications")
    op.execute("DROP TRIGGER IF EXISTS website_versions_immutable ON website_versions")
    op.execute("DROP FUNCTION IF EXISTS prevent_website_snapshot_mutation()")

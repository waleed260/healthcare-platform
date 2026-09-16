"""Make unset tenant context fail closed without invalid UUID cast errors."""
from alembic import op


revision = "0037_safe_tenant_policy_cast"
down_revision = "0036_platform_admin_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        DECLARE policy_row record;
        BEGIN
            FOR policy_row IN
                SELECT tablename, policyname
                FROM pg_policies
                WHERE schemaname = 'public' AND policyname LIKE '%_tenant_policy'
            LOOP
                EXECUTE format('DROP POLICY %I ON %I', policy_row.policyname, policy_row.tablename);
                IF policy_row.tablename = 'audit_events' THEN
                    EXECUTE format('CREATE POLICY %I ON %I USING (clinic_id = NULLIF(current_setting(''app.clinic_id'', true), '''')::uuid OR (clinic_id IS NULL AND current_setting(''app.is_platform_admin'', true) = ''true'')) WITH CHECK (clinic_id = NULLIF(current_setting(''app.clinic_id'', true), '''')::uuid OR (clinic_id IS NULL AND current_setting(''app.is_platform_admin'', true) = ''true''))', policy_row.policyname, policy_row.tablename);
                ELSE
                    EXECUTE format('CREATE POLICY %I ON %I USING (clinic_id = NULLIF(current_setting(''app.clinic_id'', true), '''')::uuid) WITH CHECK (clinic_id = NULLIF(current_setting(''app.clinic_id'', true), '''')::uuid)', policy_row.policyname, policy_row.tablename);
                END IF;
            END LOOP;
        END $$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        DECLARE policy_row record;
        BEGIN
            FOR policy_row IN
                SELECT tablename, policyname
                FROM pg_policies
                WHERE schemaname = 'public' AND policyname LIKE '%_tenant_policy'
            LOOP
                EXECUTE format('DROP POLICY %I ON %I', policy_row.policyname, policy_row.tablename);
                EXECUTE format('CREATE POLICY %I ON %I USING (clinic_id = current_setting(''app.clinic_id'', true)::uuid) WITH CHECK (clinic_id = current_setting(''app.clinic_id'', true)::uuid)', policy_row.policyname, policy_row.tablename);
            END LOOP;
        END $$;
    """)

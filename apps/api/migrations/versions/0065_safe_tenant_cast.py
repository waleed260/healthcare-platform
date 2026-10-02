"""Re-apply the NULLIF-guarded clinic_id cast to every tenant policy created after 0037.

Platform-admin sessions set app.clinic_id to '' (empty). Policies that cast it directly
(''::uuid) raise invalid-input-syntax, which broke the platform admin console. 0037 fixed
the policies that existed then; this fixes every later one, preserving the is_platform_admin
escape on upgrade_requests.
"""
from alembic import op


revision = "0065_safe_tenant_cast"
down_revision = "0064_runtime_plan_grants"
branch_labels = None
depends_on = None

PLAIN = "clinic_id = NULLIF(current_setting(''app.clinic_id'', true), '''')::uuid"
PLATFORM = PLAIN + " OR current_setting(''app.is_platform_admin'', true) = ''true''"


def upgrade() -> None:
    op.execute(f"""
        DO $$
        DECLARE policy_row record; expr text;
        BEGIN
            FOR policy_row IN
                SELECT tablename, policyname
                FROM pg_policies
                WHERE schemaname = 'public'
                  AND policyname LIKE '%_tenant_policy'
                  AND qual LIKE '%app.clinic_id%'
                  AND qual NOT LIKE '%NULLIF%'
            LOOP
                IF policy_row.tablename = 'upgrade_requests' THEN
                    expr := '{PLATFORM}';
                ELSE
                    expr := '{PLAIN}';
                END IF;
                EXECUTE format('DROP POLICY %I ON %I', policy_row.policyname, policy_row.tablename);
                EXECUTE format('CREATE POLICY %I ON %I USING (%s) WITH CHECK (%s)', policy_row.policyname, policy_row.tablename, expr, expr);
            END LOOP;
        END $$;
    """)


def downgrade() -> None:
    # Intentionally not reverted: the previous form crashes on empty tenant context.
    pass

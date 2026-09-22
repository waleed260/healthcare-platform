"""Bind temporary platform-admin support context to server-side sessions."""

from alembic import op


revision = "0044_support_context_sessions"
down_revision = "0043_owner_lifecycle_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sessions ADD COLUMN support_access_id uuid NULL")
    op.execute("ALTER TABLE sessions ADD CONSTRAINT fk_sessions_support_access FOREIGN KEY (support_access_id) REFERENCES support_access_sessions (id) ON DELETE RESTRICT")
    op.execute("CREATE INDEX ix_sessions_support_access ON sessions (support_access_id) WHERE support_access_id IS NOT NULL")
    op.execute("""
        CREATE FUNCTION prevent_non_platform_support_session()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.support_access_id IS NOT NULL
               AND NOT EXISTS (SELECT 1 FROM users WHERE id = NEW.user_id AND is_platform_admin) THEN
                RAISE EXCEPTION 'support context requires a platform administrator session';
            END IF;
            RETURN NEW;
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER sessions_support_context_platform_only
        BEFORE INSERT OR UPDATE OF support_access_id ON sessions
        FOR EACH ROW EXECUTE FUNCTION prevent_non_platform_support_session()
    """)
    op.execute("DROP POLICY support_access_sessions_tenant_policy ON support_access_sessions")
    op.execute("""
        CREATE POLICY support_access_sessions_tenant_policy ON support_access_sessions
        USING (
            clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid
            OR current_setting('app.is_platform_admin', true) = 'true'
        )
        WITH CHECK (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid)
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS sessions_support_context_platform_only ON sessions")
    op.execute("DROP FUNCTION IF EXISTS prevent_non_platform_support_session()")
    op.execute("DROP POLICY support_access_sessions_tenant_policy ON support_access_sessions")
    op.execute("""
        CREATE POLICY support_access_sessions_tenant_policy ON support_access_sessions
        USING (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid)
        WITH CHECK (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid)
    """)
    op.execute("DROP INDEX IF EXISTS ix_sessions_support_access")
    op.execute("ALTER TABLE sessions DROP CONSTRAINT IF EXISTS fk_sessions_support_access")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS support_access_id")

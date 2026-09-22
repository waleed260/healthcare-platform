"""Prevent a clinic from losing its final active owner."""

from alembic import op


revision = "0043_owner_lifecycle_integrity"
down_revision = "0042_manual_reset_permission"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION prevent_last_active_owner_role_removal()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            owner_count integer;
        BEGIN
            IF EXISTS (SELECT 1 FROM roles WHERE id = OLD.role_id AND name = 'owner') THEN
                PERFORM pg_advisory_xact_lock(hashtextextended(CAST(OLD.clinic_id AS text), 0));
                SELECT COUNT(*) INTO owner_count
                FROM users u
                JOIN user_roles ur ON ur.clinic_id = u.clinic_id AND ur.user_id = u.id
                JOIN roles r ON r.id = ur.role_id AND r.name = 'owner'
                WHERE u.clinic_id = OLD.clinic_id
                  AND u.status = 'active'
                  AND u.archived_at IS NULL;
                IF owner_count <= 1 THEN
                    RAISE EXCEPTION 'cannot remove the final active clinic owner';
                END IF;
            END IF;
            RETURN OLD;
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER user_roles_keep_active_owner
        BEFORE DELETE ON user_roles
        FOR EACH ROW EXECUTE FUNCTION prevent_last_active_owner_role_removal()
    """)
    op.execute("""
        CREATE FUNCTION prevent_last_active_owner_deactivation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            owner_count integer;
            is_owner boolean;
        BEGIN
            IF OLD.status = 'active' AND NEW.status <> 'active' THEN
                SELECT EXISTS (
                    SELECT 1 FROM user_roles ur
                    JOIN roles r ON r.id = ur.role_id AND r.name = 'owner'
                    WHERE ur.clinic_id = OLD.clinic_id AND ur.user_id = OLD.id
                ) INTO is_owner;
                IF is_owner THEN
                    PERFORM pg_advisory_xact_lock(hashtextextended(CAST(OLD.clinic_id AS text), 0));
                    SELECT COUNT(*) INTO owner_count
                    FROM users u
                    JOIN user_roles ur ON ur.clinic_id = u.clinic_id AND ur.user_id = u.id
                    JOIN roles r ON r.id = ur.role_id AND r.name = 'owner'
                    WHERE u.clinic_id = OLD.clinic_id
                      AND u.status = 'active'
                      AND u.archived_at IS NULL;
                    IF owner_count <= 1 THEN
                        RAISE EXCEPTION 'cannot deactivate the final active clinic owner';
                    END IF;
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER users_keep_active_owner
        BEFORE UPDATE OF status ON users
        FOR EACH ROW EXECUTE FUNCTION prevent_last_active_owner_deactivation()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS users_keep_active_owner ON users")
    op.execute("DROP FUNCTION IF EXISTS prevent_last_active_owner_deactivation()")
    op.execute("DROP TRIGGER IF EXISTS user_roles_keep_active_owner ON user_roles")
    op.execute("DROP FUNCTION IF EXISTS prevent_last_active_owner_role_removal()")

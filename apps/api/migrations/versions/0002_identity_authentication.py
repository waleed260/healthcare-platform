"""Create identity, session, recovery, MFA, and rate-limit tables."""
from alembic import op

revision = "0002_identity_authentication"
down_revision = "0001_tenant_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE users (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NULL REFERENCES clinics(id) ON DELETE RESTRICT,
            normalized_email text NOT NULL UNIQUE,
            display_name text NOT NULL,
            password_hash text NOT NULL,
            status text NOT NULL DEFAULT 'active',
            failed_login_count integer NOT NULL DEFAULT 0,
            locked_until timestamptz NULL,
            last_login_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            version integer NOT NULL DEFAULT 1
        )
    """)
    op.execute("""
        CREATE TABLE sessions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash char(64) NOT NULL UNIQUE,
            csrf_token_hash char(64) NOT NULL,
            mfa_verified boolean NOT NULL DEFAULT false,
            ip_hash char(64) NOT NULL,
            user_agent text NULL,
            last_seen_at timestamptz NOT NULL DEFAULT now(),
            idle_expires_at timestamptz NOT NULL,
            absolute_expires_at timestamptz NOT NULL,
            revoked_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_sessions_user_id ON sessions (user_id)")
    op.execute("CREATE INDEX ix_sessions_active ON sessions (token_hash, revoked_at)")
    op.execute("""
        CREATE TABLE staff_invitations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE RESTRICT,
            invited_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            intended_normalized_email text NOT NULL,
            token_hash char(64) NOT NULL UNIQUE,
            expires_at timestamptz NOT NULL,
            consumed_at timestamptz NULL,
            revoked_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE password_reset_tokens (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash char(64) NOT NULL UNIQUE,
            expires_at timestamptz NOT NULL,
            consumed_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE mfa_methods (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            method text NOT NULL DEFAULT 'totp',
            secret_ciphertext text NOT NULL,
            enrolled_at timestamptz NULL,
            last_used_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_mfa_methods_user_method UNIQUE (user_id, method)
        )
    """)
    op.execute("""
        CREATE TABLE recovery_codes (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            code_hash char(64) NOT NULL,
            used_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_recovery_codes_user_hash UNIQUE (user_id, code_hash)
        )
    """)
    op.execute("""
        CREATE TABLE auth_rate_limit_buckets (
            bucket_key char(64) PRIMARY KEY,
            failure_count integer NOT NULL DEFAULT 0,
            first_failure_at timestamptz NOT NULL DEFAULT now(),
            locked_until timestamptz NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON users, sessions, staff_invitations, password_reset_tokens, mfa_methods, recovery_codes, auth_rate_limit_buckets TO healthcare_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS recovery_codes")
    op.execute("DROP TABLE IF EXISTS mfa_methods")
    op.execute("DROP TABLE IF EXISTS password_reset_tokens")
    op.execute("DROP TABLE IF EXISTS staff_invitations")
    op.execute("DROP TABLE IF EXISTS sessions")
    op.execute("DROP TABLE IF EXISTS auth_rate_limit_buckets")
    op.execute("DROP TABLE IF EXISTS users")

"""Create plans, feature limits, support access, audit, and privacy workflows."""
from alembic import op
import sqlalchemy as sa

revision = "0012_governance"
down_revision = "0011_background_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE plans (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            code text NOT NULL UNIQUE,
            name text NOT NULL,
            active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE feature_limits (
            plan_id uuid NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
            feature_code text NOT NULL,
            limit_value bigint,
            enabled boolean NOT NULL DEFAULT true,
            PRIMARY KEY (plan_id, feature_code)
        )
    """)
    op.execute("""
        CREATE TABLE clinic_subscriptions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            plan_id uuid NOT NULL REFERENCES plans(id) ON DELETE RESTRICT,
            status text NOT NULL DEFAULT 'active',
            starts_at timestamptz NOT NULL DEFAULT now(),
            ends_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_clinic_subscriptions_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_clinic_subscriptions_status CHECK (status IN ('trialing', 'active', 'past_due', 'cancelled')),
            FOREIGN KEY (clinic_id) REFERENCES clinics(id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE support_access_sessions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            requested_by_user_id uuid NOT NULL,
            approved_by_user_id uuid NOT NULL,
            reason text NOT NULL,
            permissions jsonb NOT NULL DEFAULT '[]'::jsonb,
            starts_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NOT NULL,
            revoked_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_support_access_sessions_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_support_access_expiry CHECK (expires_at > starts_at AND expires_at <= starts_at + interval '60 minutes'),
            FOREIGN KEY (clinic_id) REFERENCES clinics(id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE audit_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NULL,
            actor_user_id uuid NULL,
            support_session_id uuid NULL,
            action text NOT NULL,
            entity_type text NOT NULL,
            entity_id uuid NULL,
            outcome text NOT NULL,
            request_id uuid NULL,
            ip_hash char(64) NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_audit_events_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_audit_metadata_size CHECK (octet_length(metadata::text) <= 16384),
            FOREIGN KEY (clinic_id, support_session_id) REFERENCES support_access_sessions (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE TABLE privacy_requests (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            patient_id uuid NOT NULL,
            request_type text NOT NULL,
            status text NOT NULL DEFAULT 'requested',
            reason text NOT NULL,
            requested_by_user_id uuid,
            resolved_by_user_id uuid,
            requested_at timestamptz NOT NULL DEFAULT now(),
            resolved_at timestamptz NULL,
            resolution_note text NULL,
            CONSTRAINT uq_privacy_requests_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_privacy_request_type CHECK (request_type IN ('access', 'correction', 'deletion', 'restriction')),
            CONSTRAINT ck_privacy_request_status CHECK (status IN ('requested', 'in_review', 'approved', 'rejected', 'completed')),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES patients (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, requested_by_user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, resolved_by_user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    op.execute("INSERT INTO plans (code, name) VALUES ('starter', 'Starter') ON CONFLICT DO NOTHING")
    op.execute("INSERT INTO plans (code, name) VALUES ('clinic', 'Clinic') ON CONFLICT DO NOTHING")
    for table in ("clinic_subscriptions", "support_access_sessions", "audit_events", "privacy_requests"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(sa.text(f"CREATE POLICY {table}_tenant_policy ON {table} USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)"))
    op.execute("CREATE INDEX ix_audit_events_clinic_created ON audit_events (clinic_id, created_at DESC)")
    op.execute("CREATE INDEX ix_privacy_requests_clinic_status ON privacy_requests (clinic_id, status, requested_at)")
    op.execute("GRANT SELECT, INSERT, UPDATE ON clinic_subscriptions, support_access_sessions, audit_events, privacy_requests TO healthcare_runtime")
    op.execute("""
        CREATE FUNCTION prevent_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'audit_events are append-only'; END;
        $$
    """)
    op.execute("CREATE TRIGGER audit_events_immutable BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation()")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_events_immutable ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_mutation()")
    op.drop_index("ix_privacy_requests_clinic_status", table_name="privacy_requests")
    op.drop_index("ix_audit_events_clinic_created", table_name="audit_events")
    for table in ("privacy_requests", "audit_events", "support_access_sessions", "clinic_subscriptions", "feature_limits", "plans"):
        op.execute(f"DROP TABLE IF EXISTS {table}")

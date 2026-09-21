"""Complete missing inventory tables and allow multiple daily branch intervals."""
from alembic import op
import sqlalchemy as sa


revision = "0035_inventory_and_hours"
down_revision = "0034_privacy_identity_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Migration 0013 replaces the original one-row-per-day constraint with
    # this interval-aware constraint. Drop the current constraint before
    # introducing the indexed multi-interval variant.
    op.drop_constraint("uq_branch_hours_interval", "branch_hours", type_="unique")
    op.add_column("branch_hours", sa.Column("interval_index", sa.SmallInteger(), nullable=False, server_default="0"))
    op.create_check_constraint("ck_branch_hours_interval_index", "branch_hours", "interval_index >= 0")
    op.create_unique_constraint("uq_branch_hours_interval", "branch_hours", ["clinic_id", "branch_id", "weekday", "interval_index"])

    op.execute("""
        CREATE TABLE doctor_rooms (
            clinic_id uuid NOT NULL,
            doctor_id uuid NOT NULL,
            room_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (clinic_id, doctor_id, room_id),
            FOREIGN KEY (clinic_id, doctor_id) REFERENCES doctor_profiles (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, room_id) REFERENCES rooms (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE access_tokens (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NULL,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash char(64) NOT NULL UNIQUE,
            purpose text NOT NULL,
            expires_at timestamptz NOT NULL,
            consumed_at timestamptz NULL,
            revoked_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_access_tokens_clinic_id UNIQUE (clinic_id, id)
        )
    """)
    op.execute("""
        CREATE TABLE system_announcements (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            title text NOT NULL,
            body text NOT NULL,
            severity text NOT NULL DEFAULT 'info',
            starts_at timestamptz NOT NULL DEFAULT now(),
            ends_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_system_announcements_severity CHECK (severity IN ('info', 'warning', 'critical')),
            CONSTRAINT ck_system_announcements_window CHECK (ends_at IS NULL OR ends_at > starts_at)
        )
    """)
    for table in ("doctor_rooms", "access_tokens"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(sa.text(f"CREATE POLICY {table}_tenant_policy ON {table} USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)"))
    op.execute("CREATE INDEX ix_access_tokens_active ON access_tokens (clinic_id, purpose, expires_at) WHERE consumed_at IS NULL AND revoked_at IS NULL")
    op.execute("CREATE INDEX ix_system_announcements_window ON system_announcements (starts_at, ends_at)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON doctor_rooms, access_tokens TO healthcare_runtime")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON system_announcements TO healthcare_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS system_announcements")
    op.execute("DROP TABLE IF EXISTS access_tokens")
    op.execute("DROP TABLE IF EXISTS doctor_rooms")
    op.drop_constraint("uq_branch_hours_interval", "branch_hours", type_="unique")
    op.drop_constraint("ck_branch_hours_interval_index", "branch_hours", type_="check")
    op.drop_column("branch_hours", "interval_index")
    op.create_unique_constraint("uq_branch_hours_day", "branch_hours", ["clinic_id", "branch_id", "weekday"])

"""Add recurring availability and blocking records for slot calculation."""
from alembic import op
import sqlalchemy as sa

revision = "0013_scheduling"
down_revision = "0012_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_branch_hours_day", "branch_hours", type_="unique")
    op.create_unique_constraint("uq_branch_hours_interval", "branch_hours", ["clinic_id", "branch_id", "weekday", "opens_at", "closes_at"])
    op.execute("""
        CREATE TABLE availability_rules (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(), clinic_id uuid NOT NULL, branch_id uuid NOT NULL,
            doctor_id uuid NOT NULL, service_id uuid NULL, weekday smallint NOT NULL CHECK (weekday BETWEEN 0 AND 6),
            starts_at time NOT NULL, ends_at time NOT NULL, effective_from date NOT NULL, effective_to date NULL,
            slot_cadence_minutes integer NOT NULL DEFAULT 15 CHECK (slot_cadence_minutes > 0),
            created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_availability_rules_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_availability_rule_time CHECK (starts_at < ends_at),
            CONSTRAINT ck_availability_rule_dates CHECK (effective_to IS NULL OR effective_from <= effective_to),
            FOREIGN KEY (clinic_id, branch_id) REFERENCES branches (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, doctor_id) REFERENCES doctor_profiles (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, service_id) REFERENCES services (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE leave_blocks (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(), clinic_id uuid NOT NULL, doctor_id uuid NOT NULL,
            branch_id uuid NULL, starts_at timestamptz NOT NULL, ends_at timestamptz NOT NULL, reason text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(), CONSTRAINT uq_leave_blocks_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_leave_block_time CHECK (starts_at < ends_at),
            FOREIGN KEY (clinic_id, doctor_id) REFERENCES doctor_profiles (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, branch_id) REFERENCES branches (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE blocked_slots (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(), clinic_id uuid NOT NULL, branch_id uuid NOT NULL,
            doctor_id uuid NULL, starts_at timestamptz NOT NULL, ends_at timestamptz NOT NULL, reason text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(), CONSTRAINT uq_blocked_slots_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_blocked_slot_time CHECK (starts_at < ends_at),
            FOREIGN KEY (clinic_id, branch_id) REFERENCES branches (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, doctor_id) REFERENCES doctor_profiles (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE resource_blocks (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(), clinic_id uuid NOT NULL, resource_id uuid NOT NULL,
            starts_at timestamptz NOT NULL, ends_at timestamptz NOT NULL, reason text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(), CONSTRAINT uq_resource_blocks_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_resource_block_time CHECK (starts_at < ends_at),
            FOREIGN KEY (clinic_id, resource_id) REFERENCES resources (clinic_id, id) ON DELETE CASCADE
        )
    """)
    for table in ("availability_rules", "leave_blocks", "blocked_slots", "resource_blocks"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(sa.text(f"CREATE POLICY {table}_tenant_policy ON {table} USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)"))
    op.execute("CREATE INDEX ix_availability_rules_lookup ON availability_rules (clinic_id, branch_id, doctor_id, weekday, effective_from)")
    op.execute("CREATE INDEX ix_leave_blocks_lookup ON leave_blocks (clinic_id, doctor_id, starts_at, ends_at)")
    op.execute("CREATE INDEX ix_blocked_slots_lookup ON blocked_slots (clinic_id, branch_id, doctor_id, starts_at, ends_at)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON availability_rules, leave_blocks, blocked_slots, resource_blocks TO healthcare_runtime")


def downgrade() -> None:
    for table in ("resource_blocks", "blocked_slots", "leave_blocks", "availability_rules"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
    op.drop_constraint("uq_branch_hours_interval", "branch_hours", type_="unique")
    op.create_unique_constraint("uq_branch_hours_day", "branch_hours", ["clinic_id", "branch_id", "weekday"])

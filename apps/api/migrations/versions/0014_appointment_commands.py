"""Add dedicated appointment transition and rescheduling command fields."""
from alembic import op
import sqlalchemy as sa

revision = "0014_appointment_commands"
down_revision = "0013_scheduling"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for code, description in (
        ("appointment.approve", "Approve or reject requested appointments"),
        ("appointment.cancel", "Cancel appointments"),
        ("appointment.reschedule", "Reschedule appointments"),
        ("appointment.check_in", "Check patients in"),
    ):
        op.execute(sa.text("INSERT INTO permissions (code, description) VALUES (:code, :description) ON CONFLICT (code) DO NOTHING").bindparams(code=code, description=description))
    for role in ("owner", "manager", "doctor", "receptionist"):
        for code in ("appointment.approve", "appointment.cancel", "appointment.reschedule", "appointment.check_in"):
            op.execute(sa.text("INSERT INTO role_permissions (role_id, permission_code) SELECT r.id, :code FROM roles r WHERE r.name = :role ON CONFLICT DO NOTHING").bindparams(role=role, code=code))
    op.add_column("appointments", sa.Column("supersedes_appointment_id", sa.Uuid(), nullable=True))
    op.add_column("appointments", sa.Column("cancellation_reason", sa.Text(), nullable=True))
    op.add_column("appointments", sa.Column("status_changed_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.create_foreign_key("fk_appointments_supersedes_tenant", "appointments", "appointments", ["clinic_id", "supersedes_appointment_id"], ["clinic_id", "id"], ondelete="RESTRICT")
    op.create_index("ix_appointments_supersedes", "appointments", ["clinic_id", "supersedes_appointment_id"])


def downgrade() -> None:
    op.drop_index("ix_appointments_supersedes", table_name="appointments")
    op.drop_constraint("fk_appointments_supersedes_tenant", "appointments", type_="foreignkey")
    op.drop_column("appointments", "status_changed_at")
    op.drop_column("appointments", "cancellation_reason")
    op.drop_column("appointments", "supersedes_appointment_id")

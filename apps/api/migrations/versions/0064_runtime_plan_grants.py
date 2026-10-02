"""Grant the runtime role the plan tables it already queries (no grant existed since 0012)."""
from alembic import op

revision = "0064_runtime_plan_grants"
down_revision = "0063_provider_commissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Least privilege: plans/limits are created and edited by platform admins through the API; never deleted.
    op.execute("GRANT SELECT, INSERT, UPDATE ON plans, feature_limits TO healthcare_runtime")


def downgrade() -> None:
    op.execute("REVOKE SELECT, INSERT, UPDATE ON plans, feature_limits FROM healthcare_runtime")

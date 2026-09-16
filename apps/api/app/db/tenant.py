from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session


class TenantContextError(RuntimeError):
    """Raised when a clinic-owned transaction has no validated tenant context."""


def set_tenant_context(db: Session | Connection, clinic_id: UUID, user_id: UUID | None = None) -> None:
    """Set transaction-local context; callers must validate the session first."""
    if not clinic_id:
        raise TenantContextError("clinic_id is required")
    db.execute(text("SELECT set_config('app.clinic_id', :clinic_id, true)"), {"clinic_id": str(clinic_id)})
    if user_id is not None:
        db.execute(text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": str(user_id)})


def set_platform_context(db: Session | Connection, user_id: UUID) -> None:
    """Mark a validated platform-admin transaction without selecting a clinic."""
    db.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
    db.execute(text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": str(user_id)})


def require_tenant_context(db: Session | Connection) -> UUID:
    value = db.execute(text("SELECT current_setting('app.clinic_id', true)")).scalar_one_or_none()
    if not value:
        raise TenantContextError("tenant context is not set")
    return UUID(value)

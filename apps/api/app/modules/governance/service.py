from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def active_support_permissions(db: Session, clinic_id: UUID, access_id: UUID) -> set[str]:
    """Return the bounded permission grant for an unexpired, non-revoked support session."""
    row = db.execute(text("""
        SELECT permissions
        FROM support_access_sessions
        WHERE clinic_id = :clinic_id AND id = :id
          AND revoked_at IS NULL AND starts_at <= now() AND expires_at > now()
    """), {"clinic_id": clinic_id, "id": access_id}).scalar_one_or_none()
    return set(row or [])


def require_support_permission(db: Session, clinic_id: UUID, access_id: UUID, permission: str) -> None:
    if permission not in active_support_permissions(db, clinic_id, access_id):
        raise PermissionError("support access is missing, expired, revoked, or does not grant this permission")

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def record_event(
    db: Session,
    *,
    clinic_id: UUID | None,
    actor_user_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    outcome: str,
    request_id: UUID | None = None,
    ip_hash: str | None = None,
    metadata: Mapping[str, object] | None = None,
) -> UUID:
    """Record bounded metadata only; callers must never pass clinical bodies or tokens."""
    if metadata and len(str(dict(metadata))) > 16000:
        raise ValueError("audit metadata is too large")
    row = db.execute(text("""
        INSERT INTO audit_events (clinic_id, actor_user_id, action, entity_type, entity_id, outcome, request_id, ip_hash, metadata)
        VALUES (:clinic_id, :actor_user_id, :action, :entity_type, :entity_id, :outcome, :request_id, :ip_hash, CAST(:metadata AS jsonb))
        RETURNING id
    """), {"clinic_id": clinic_id, "actor_user_id": actor_user_id, "action": action, "entity_type": entity_type, "entity_id": entity_id, "outcome": outcome, "request_id": request_id, "ip_hash": ip_hash, "metadata": __import__("json").dumps(dict(metadata or {}), default=str)}).scalar_one()
    return row

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.tenant import set_tenant_context


class FeatureLimitExceeded(RuntimeError):
    code = "FEATURE_LIMIT_EXCEEDED"


def consume_feature_limit(
    db: Session,
    clinic_id: UUID,
    feature_code: str,
    increment: int,
    *,
    period_start: date | None = None,
) -> None:
    """Consume a configured feature limit atomically.

    A missing subscription or feature limit is treated as unlimited until an
    administrator configures the clinic's plan. Once configured, the guarded
    upsert makes concurrent increments race-safe.
    """
    if increment <= 0:
        raise ValueError("increment must be positive")
    set_tenant_context(db, clinic_id)
    limit = db.execute(text("""
        SELECT fl.limit_value
        FROM clinic_subscriptions cs
        JOIN feature_limits fl ON fl.plan_id = cs.plan_id
        WHERE cs.clinic_id = :clinic_id
          AND cs.status IN ('trialing', 'active')
          AND cs.starts_at <= now()
          AND (cs.ends_at IS NULL OR cs.ends_at > now())
          AND fl.feature_code = :feature_code
          AND fl.enabled = true
        ORDER BY cs.updated_at DESC
        LIMIT 1
    """), {"clinic_id": clinic_id, "feature_code": feature_code}).scalar_one_or_none()
    if limit is None:
        return

    start = period_start or datetime.now(timezone.utc).date()
    updated = db.execute(text("""
        INSERT INTO clinic_feature_usage (clinic_id, feature_code, period_start, usage_count)
        VALUES (:clinic_id, :feature_code, :period_start, :increment)
        ON CONFLICT (clinic_id, feature_code, period_start) DO UPDATE
        SET usage_count = clinic_feature_usage.usage_count + EXCLUDED.usage_count,
            updated_at = now()
        WHERE clinic_feature_usage.usage_count + EXCLUDED.usage_count <= :limit_value
        RETURNING usage_count
    """), {"clinic_id": clinic_id, "feature_code": feature_code, "period_start": start, "increment": increment, "limit_value": limit}).scalar_one_or_none()
    if updated is None:
        raise FeatureLimitExceeded(feature_code)

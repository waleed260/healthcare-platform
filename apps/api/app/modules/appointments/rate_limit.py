from __future__ import annotations

from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import hash_ip, hash_token


def consume_public_management_limit(
    db: Session,
    *,
    clinic_id: object,
    reference: str,
    ip_address: str,
    maximum: int = 20,
    window: timedelta = timedelta(minutes=1),
) -> bool:
    """Consume a privacy-preserving fixed-window request bucket atomically."""
    if maximum <= 0 or window.total_seconds() <= 0:
        raise ValueError("rate-limit parameters must be positive")
    bucket_key = hash_token(f"public-management:{clinic_id}:{reference.strip().casefold()}:{hash_ip(ip_address)}")
    row = db.execute(text("""
        INSERT INTO public_rate_limit_buckets (bucket_key, window_started_at, request_count)
        VALUES (:bucket_key, now(), 1)
        ON CONFLICT (bucket_key) DO UPDATE SET
            request_count = CASE
                WHEN public_rate_limit_buckets.window_started_at <= now() - (:window_seconds * interval '1 second') THEN 1
                ELSE public_rate_limit_buckets.request_count + 1
            END,
            window_started_at = CASE
                WHEN public_rate_limit_buckets.window_started_at <= now() - (:window_seconds * interval '1 second') THEN now()
                ELSE public_rate_limit_buckets.window_started_at
            END,
            updated_at = now()
        RETURNING request_count
    """), {"bucket_key": bucket_key, "window_seconds": int(window.total_seconds())}).scalar_one()
    return row <= maximum

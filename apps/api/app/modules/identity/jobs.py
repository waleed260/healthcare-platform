"""Periodic cleanup of expired auth data (sessions, rate-limit buckets, reset tokens)."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.tenant import set_tenant_context

LOGGER = logging.getLogger("healthcare.identity.cleanup")

BATCH_SIZE = 500


def run_session_cleanup(db: Session, clinic_id: UUID) -> int:
    set_tenant_context(db, clinic_id)
    total = 0

    deleted = db.execute(text("""
        DELETE FROM sessions WHERE id IN (
            SELECT id FROM sessions
            WHERE (revoked_at IS NOT NULL AND revoked_at < now() - interval '24 hours')
               OR idle_expires_at < now() - interval '24 hours'
               OR absolute_expires_at < now() - interval '24 hours'
            LIMIT :batch
        )
    """), {"batch": BATCH_SIZE}).rowcount
    total += deleted
    LOGGER.info("cleaned %d expired sessions", deleted)

    deleted = db.execute(text("""
        DELETE FROM auth_rate_limit_buckets WHERE bucket_key IN (
            SELECT bucket_key FROM auth_rate_limit_buckets
            WHERE updated_at < now() - interval '1 hour'
              AND (locked_until IS NULL OR locked_until < now())
            LIMIT :batch
        )
    """), {"batch": BATCH_SIZE}).rowcount
    total += deleted
    LOGGER.info("cleaned %d stale rate-limit buckets", deleted)

    deleted = db.execute(text("""
        DELETE FROM password_reset_tokens WHERE id IN (
            SELECT id FROM password_reset_tokens
            WHERE consumed_at IS NOT NULL AND consumed_at < now() - interval '24 hours'
               OR expires_at < now() - interval '24 hours'
            LIMIT :batch
        )
    """), {"batch": BATCH_SIZE}).rowcount
    total += deleted
    LOGGER.info("cleaned %d expired reset tokens", deleted)

    db.commit()
    return total

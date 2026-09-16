from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.tenant import set_tenant_context
from app.modules.files.storage import read_private_object


MAX_WEBSITE_IMAGE_BYTES = 8 * 1024 * 1024
MAGIC_PREFIXES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}


def validate_image_magic(mime_type: str, content_prefix: bytes) -> None:
    expected = MAGIC_PREFIXES.get(mime_type)
    if expected is None or not any(content_prefix.startswith(prefix) for prefix in expected):
        raise ValueError("file contents do not match the declared image MIME type")
    if mime_type == "image/webp" and content_prefix[8:12] != b"WEBP":
        raise ValueError("file contents do not match the declared image MIME type")


def scan_website_media_bytes(db: Session, clinic_id: UUID, media_id: UUID, content: bytes) -> str:
    set_tenant_context(db, clinic_id)
    media = db.execute(text("""
        SELECT id, storage_key, mime_type, size_bytes, content_sha256
        FROM website_media
        WHERE clinic_id = :clinic_id AND id = :media_id AND is_public = false
        FOR UPDATE
    """), {"clinic_id": clinic_id, "media_id": media_id}).mappings().one_or_none()
    if media is None:
        raise ValueError("website media not found")
    outcome = "clean"
    reason = None
    if media["size_bytes"] is None or media["content_sha256"] is None or len(content) != media["size_bytes"] or hashlib.sha256(content).hexdigest() != media["content_sha256"].lower():
        outcome, reason = "scan_failed", "stored object does not match declared size or SHA-256 digest"
    else:
        try:
            validate_image_magic(media["mime_type"], content[:16])
        except ValueError:
            outcome, reason = "quarantined", "image signature does not match the declared MIME type"
    db.execute(text("""
        UPDATE website_media
        SET scan_status = :outcome, scan_failure_reason = :reason
        WHERE clinic_id = :clinic_id AND id = :media_id
    """), {"clinic_id": clinic_id, "media_id": media_id, "outcome": outcome, "reason": reason})
    db.execute(text("""
        INSERT INTO website_media_scan_events
          (clinic_id, media_id, engine, signature_version, outcome, failure_reason)
        VALUES (:clinic_id, :media_id, 'builtin-signature', '1', :outcome, :reason)
    """), {"clinic_id": clinic_id, "media_id": media_id, "outcome": outcome, "reason": reason})
    db.commit()
    return outcome


def run_next_stored_website_media_scan(db: Session, clinic_id: UUID) -> str | None:
    from app.modules.operations.jobs import claim_next_job, complete_job, fail_job

    job = claim_next_job(db, clinic_id, job_type="website_media_scan")
    if job is None:
        return None
    media_id = UUID(job["job_key"].removeprefix("website-media-scan:"))
    try:
        key = db.execute(text("SELECT storage_key FROM website_media WHERE clinic_id = :clinic_id AND id = :media_id"), {"clinic_id": clinic_id, "media_id": media_id}).scalar_one()
        outcome = scan_website_media_bytes(db, clinic_id, media_id, read_private_object(key))
        complete_job(db, clinic_id, job["id"])
        db.commit()
        return outcome
    except Exception:
        fail_job(db, clinic_id, job["id"], attempts=job["attempts"], failure_code="WEBSITE_MEDIA_SCAN_FAILED")
        db.commit()
        return "scan_failed"

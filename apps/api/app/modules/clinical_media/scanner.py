from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.tenant import set_tenant_context
from app.modules.files.storage import read_private_object
from app.modules.operations.jobs import claim_next_job, complete_job, fail_job
from app.modules.websites.scanner import validate_image_magic


MAX_PATIENT_MEDIA_BYTES = 8 * 1024 * 1024


def scan_patient_media_bytes(db: Session, clinic_id: UUID, media_id: UUID, content: bytes) -> str:
    set_tenant_context(db, clinic_id)
    media = db.execute(text("""
        SELECT id, mime_type, size_bytes, content_sha256
        FROM patient_media
        WHERE clinic_id = :clinic_id AND id = :media_id AND archived_at IS NULL
        FOR UPDATE
    """), {"clinic_id": clinic_id, "media_id": media_id}).mappings().one_or_none()
    if media is None:
        raise ValueError("patient media not found")
    outcome, reason = "clean", None
    if len(content) != media["size_bytes"] or hashlib.sha256(content).hexdigest() != media["content_sha256"].lower():
        outcome, reason = "scan_failed", "stored object does not match declared size or SHA-256 digest"
    else:
        try:
            validate_image_magic(media["mime_type"], content[:16])
        except ValueError:
            outcome, reason = "quarantined", "image signature does not match the declared MIME type"
    db.execute(text("UPDATE patient_media SET scan_status = :outcome, scan_failure_reason = :reason, updated_at = now() WHERE clinic_id = :clinic_id AND id = :media_id"), {"clinic_id": clinic_id, "media_id": media_id, "outcome": outcome, "reason": reason})
    db.execute(text("""
        INSERT INTO patient_media_scan_events (clinic_id, media_id, engine, signature_version, outcome, failure_reason)
        VALUES (:clinic_id, :media_id, 'builtin-signature', '1', :outcome, :reason)
    """), {"clinic_id": clinic_id, "media_id": media_id, "outcome": outcome, "reason": reason})
    db.commit()
    return outcome


def run_next_stored_patient_media_scan(db: Session, clinic_id: UUID) -> str | None:
    job = claim_next_job(db, clinic_id, job_type="patient_media_scan")
    if job is None:
        return None
    media_id = UUID(job["job_key"].removeprefix("patient-media-scan:"))
    try:
        key = db.execute(text("SELECT storage_key FROM patient_media WHERE clinic_id = :clinic_id AND id = :media_id"), {"clinic_id": clinic_id, "media_id": media_id}).scalar_one()
        outcome = scan_patient_media_bytes(db, clinic_id, media_id, read_private_object(key))
        complete_job(db, clinic_id, job["id"])
        db.commit()
        return outcome
    except Exception:
        fail_job(db, clinic_id, job["id"], attempts=job["attempts"], failure_code="PATIENT_MEDIA_SCAN_FAILED")
        db.commit()
        return "scan_failed"

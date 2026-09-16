from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.files.scanner import scan_document_bytes
from app.modules.files.storage import read_private_object
from app.modules.operations.jobs import claim_next_job, complete_job, fail_job


def run_next_document_scan(db: Session, clinic_id: UUID, content_loader: Callable[[UUID], bytes]) -> str | None:
    """Process one queued document scan using a trusted server-side object loader."""
    job = claim_next_job(db, clinic_id, job_type="document_scan")
    if job is None:
        return None
    document_id = UUID(job["job_key"].removeprefix("document-scan:"))
    try:
        outcome = scan_document_bytes(db, clinic_id, document_id, content_loader(document_id))
        complete_job(db, clinic_id, job["id"])
        db.commit()
        return outcome
    except Exception:
        fail_job(db, clinic_id, job["id"], attempts=job["attempts"], failure_code="DOCUMENT_SCAN_FAILED")
        db.commit()
        return "scan_failed"


def run_next_stored_document_scan(db: Session, clinic_id: UUID) -> str | None:
    """Process one scan using the configured private-object adapter."""
    return run_next_document_scan(db, clinic_id, lambda document_id: read_private_object(_storage_key_for(db, clinic_id, document_id)))


def _storage_key_for(db: Session, clinic_id: UUID, document_id: UUID) -> str:
    from sqlalchemy import text

    key = db.execute(text("SELECT storage_key FROM patient_documents WHERE clinic_id = :clinic_id AND id = :document_id AND archived_at IS NULL"), {"clinic_id": clinic_id, "document_id": document_id}).scalar_one_or_none()
    if key is None:
        raise ValueError("document not found")
    return key

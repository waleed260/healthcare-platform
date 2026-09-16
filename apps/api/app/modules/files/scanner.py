from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.tenant import set_tenant_context
from app.modules.files.service import validate_magic_bytes


def scan_document_bytes(db: Session, clinic_id: UUID, document_id: UUID, content: bytes) -> str:
    """Record a scanner decision without persisting document contents.

    The scanner owns transitions out of ``pending_scan``. It verifies the stored
    size and digest before accepting a clean result and quarantines mismatched
    media signatures.
    """
    set_tenant_context(db, clinic_id)
    document = db.execute(text("""
        SELECT id, mime_type, size_bytes, content_sha256
        FROM patient_documents
        WHERE clinic_id = :clinic_id AND id = :document_id AND archived_at IS NULL
        FOR UPDATE
    """), {"clinic_id": clinic_id, "document_id": document_id}).mappings().one_or_none()
    if document is None:
        raise ValueError("document not found")

    outcome = "clean"
    reason = None
    if len(content) != document["size_bytes"] or hashlib.sha256(content).hexdigest() != document["content_sha256"].strip().lower():
        outcome = "scan_failed"
        reason = "stored object does not match declared size or SHA-256 digest"
    else:
        try:
            validate_magic_bytes(document["mime_type"], content[:16])
        except ValueError:
            outcome = "quarantined"
            reason = "file signature does not match the declared MIME type"

    db.execute(text("""
        UPDATE patient_documents
        SET scan_status = :outcome, scan_failure_reason = :reason, updated_at = now(), version = version + 1
        WHERE clinic_id = :clinic_id AND id = :document_id
    """), {"clinic_id": clinic_id, "document_id": document_id, "outcome": outcome, "reason": reason})
    db.execute(text("""
        INSERT INTO file_scan_events (id, clinic_id, document_id, engine, signature_version, outcome, failure_reason)
        VALUES (:id, :clinic_id, :document_id, 'builtin-signature', '1', :outcome, :reason)
    """), {"id": uuid4(), "clinic_id": clinic_id, "document_id": document_id, "outcome": outcome, "reason": reason})
    db.commit()
    return outcome

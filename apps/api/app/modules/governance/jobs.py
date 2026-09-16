from __future__ import annotations

import json
import secrets
from datetime import timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import hash_token
from app.db.tenant import set_tenant_context
from app.modules.files.storage import delete_private_object, put_private_object
from app.modules.operations.jobs import claim_next_job, complete_job, fail_job


def _rows(db: Session, query: str, params: dict[str, object]) -> list[dict]:
    return [dict(row) for row in db.execute(text(query), params).mappings().all()]


def _build_export(db: Session, clinic_id: UUID, job: dict) -> dict[str, object]:
    export = db.execute(text("""
        SELECT id, export_type, patient_id, privacy_request_id
        FROM export_jobs
        WHERE clinic_id = :clinic_id AND id = :id
        FOR UPDATE
    """), {"clinic_id": clinic_id, "id": job["export_id"]}).mappings().one_or_none()
    if export is None:
        raise ValueError("export job not found")
    if export["export_type"] == "audit":
        return {"export_type": "audit", "events": _rows(db, """
            SELECT actor_user_id, action, entity_type, entity_id, outcome, request_id, ip_hash, metadata, created_at
            FROM audit_events WHERE clinic_id = :clinic_id ORDER BY created_at, id
        """, {"clinic_id": clinic_id})}
    patient = db.execute(text("""
        SELECT id, patient_number, full_name, normalized_email, normalized_phone,
               date_of_birth, status, duplicate_of, created_at, updated_at
        FROM patients WHERE clinic_id = :clinic_id AND id = :patient_id
    """), {"clinic_id": clinic_id, "patient_id": export["patient_id"]}).mappings().one_or_none()
    if patient is None:
        raise ValueError("export patient not found")
    patient_id = export["patient_id"]
    return {
        "export_type": "patient_access",
        "patient": dict(patient),
        "contacts": _rows(db, "SELECT contact_type, value, is_primary, created_at, updated_at FROM patient_contacts WHERE clinic_id = :clinic_id AND patient_id = :patient_id ORDER BY created_at", {"clinic_id": clinic_id, "patient_id": patient_id}),
        "notes": _rows(db, "SELECT note_type, visibility, body, created_at, updated_at FROM patient_notes WHERE clinic_id = :clinic_id AND patient_id = :patient_id AND archived_at IS NULL ORDER BY created_at", {"clinic_id": clinic_id, "patient_id": patient_id}),
        "consents": _rows(db, "SELECT consent_type, status, version, recorded_at, withdrawn_at, metadata FROM consent_records WHERE clinic_id = :clinic_id AND patient_id = :patient_id ORDER BY recorded_at", {"clinic_id": clinic_id, "patient_id": patient_id}),
        "appointments": _rows(db, "SELECT reference, starts_at, ends_at, status, source, created_at FROM appointments WHERE clinic_id = :clinic_id AND patient_id = :patient_id ORDER BY starts_at", {"clinic_id": clinic_id, "patient_id": patient_id}),
        "documents": _rows(db, "SELECT id, original_filename, mime_type, size_bytes, scan_status, created_at, archived_at FROM patient_documents WHERE clinic_id = :clinic_id AND patient_id = :patient_id ORDER BY created_at", {"clinic_id": clinic_id, "patient_id": patient_id}),
    }


def run_next_export_job(db: Session, clinic_id: UUID) -> str | None:
    job = claim_next_job(db, clinic_id, job_type="export")
    if job is None:
        return None
    export_id = UUID(job["job_key"].removeprefix("export:"))
    job["export_id"] = export_id
    try:
        set_tenant_context(db, clinic_id)
        db.execute(text("UPDATE export_jobs SET status = 'running' WHERE clinic_id = :clinic_id AND id = :id AND status = 'queued'"), {"clinic_id": clinic_id, "id": export_id})
        document = _build_export(db, clinic_id, job)
        storage_key = f"exports/{clinic_id}/{export_id}.json"
        put_private_object(storage_key, json.dumps(document, default=str, sort_keys=True).encode("utf-8"))
        db.execute(text("""
            UPDATE export_jobs
            SET status = 'completed', storage_key = :storage_key,
                expires_at = now() + interval '24 hours', completed_at = now(), failure_code = NULL
            WHERE clinic_id = :clinic_id AND id = :id
        """), {"clinic_id": clinic_id, "id": export_id, "storage_key": storage_key})
        complete_job(db, clinic_id, job["id"])
        db.commit()
        return "completed"
    except Exception:
        db.execute(text("UPDATE export_jobs SET status = 'failed', failure_code = 'EXPORT_GENERATION_FAILED' WHERE clinic_id = :clinic_id AND id = :id"), {"clinic_id": clinic_id, "id": export_id})
        fail_job(db, clinic_id, job["id"], attempts=job["attempts"], failure_code="EXPORT_GENERATION_FAILED")
        db.commit()
        return "failed"


def run_expired_artifact_cleanup(db: Session, clinic_id: UUID) -> dict[str, int]:
    """Remove only short-lived delivery/preview artifacts for one clinic.

    Patient, audit, and export metadata rows are retained. The private export
    object and download token are removed after the delivery window, while
    expired or revoked website preview tokens are no longer usable.
    """
    set_tenant_context(db, clinic_id)
    expired_exports = db.execute(text("""
        SELECT id, storage_key
        FROM export_jobs
        WHERE clinic_id = :clinic_id
          AND status = 'completed'
          AND expires_at IS NOT NULL
          AND expires_at <= now()
        FOR UPDATE
    """), {"clinic_id": clinic_id}).mappings().all()
    expired_count = 0
    for export in expired_exports:
        if export["storage_key"]:
            delete_private_object(export["storage_key"])
        db.execute(text("""
            UPDATE export_jobs
            SET status = 'expired', storage_key = NULL, download_token_hash = NULL
            WHERE clinic_id = :clinic_id AND id = :id AND status = 'completed'
        """), {"clinic_id": clinic_id, "id": export["id"]})
        expired_count += 1

    preview_result = db.execute(text("""
        DELETE FROM website_preview_tokens
        WHERE clinic_id = :clinic_id
          AND (expires_at <= now() OR revoked_at IS NOT NULL)
    """), {"clinic_id": clinic_id})
    db.commit()
    return {"exports_expired": expired_count, "preview_tokens_deleted": preview_result.rowcount}

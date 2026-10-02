from __future__ import annotations

import hashlib
from datetime import date
from uuid import UUID, uuid4

from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import decode_cursor, encode_cursor
from app.db.session import get_db
from app.modules.audit.service import record_event
from app.modules.clinical.routes import _authorized, _write_authorized
from app.modules.clinical_media.scanner import MAX_PATIENT_MEDIA_BYTES
from app.modules.clinical_media.schemas import PatientMediaApproval, PatientMediaCreate, PatientMediaRevoke
from app.modules.crm.routes import _require_patient
from app.modules.files.storage import delete_private_object, put_private_object
from app.modules.identity.routes import _error
from app.modules.websites.scanner import validate_image_magic


router = APIRouter(prefix="/api/v1/patients", tags=["clinical-media"])


def _media_or_404(db: Session, session: dict, patient_id: UUID, media_id: UUID) -> dict:
    row = db.execute(text("""
        SELECT id, patient_id, treatment_plan_item_id, provider_user_id, captured_on, media_kind, mime_type,
               size_bytes, scan_status, scan_failure_reason, approval_status, approved_for_website,
               consent_record_id, approved_by_user_id, approved_at, version, created_at, updated_at
        FROM patient_media
        WHERE clinic_id = :clinic_id AND patient_id = :patient_id AND id = :media_id AND archived_at IS NULL
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "media_id": media_id}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Patient media not found.", status.HTTP_404_NOT_FOUND)
    return dict(row)


@router.get("/{patient_id}/media")
def media_list(patient_id: UUID, request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=100, ge=1, le=200), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "patient.media.read")
    _require_patient(db, session, patient_id)
    cursor_values = decode_cursor(cursor, "patient_media") if cursor else None
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid or expired.", status.HTTP_400_BAD_REQUEST)
    rows = db.execute(text("""
        SELECT id, treatment_plan_item_id, provider_user_id, captured_on, media_kind, mime_type, size_bytes,
               scan_status, scan_failure_reason, approval_status, approved_for_website, consent_record_id,
               approved_by_user_id, approved_at, version, created_at, updated_at
        FROM patient_media
        WHERE clinic_id = :clinic_id AND patient_id = :patient_id AND archived_at IS NULL
          AND (:after_id IS NULL OR captured_on < :after_captured OR (captured_on = :after_captured AND id < :after_id))
        ORDER BY captured_on DESC, id DESC
        LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id,
           "after_captured": date.fromisoformat(cursor_values["captured_on"]) if cursor_values else None,
           "after_id": UUID(cursor_values["id"]) if cursor_values else None,
           "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = list(rows[:limit])
    next_cursor = encode_cursor("patient_media", {"captured_on": rows[-1]["captured_on"].isoformat(), "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@router.post("/{patient_id}/media/upload", status_code=status.HTTP_201_CREATED)
async def media_upload(patient_id: UUID, request: Request, media_kind: str = "other", captured_on: date | None = None, treatment_plan_item_id: UUID | None = None, provider_user_id: UUID | None = None, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "patient.media.write", csrf_token)
    _require_patient(db, session, patient_id)
    payload = PatientMediaCreate(media_kind=media_kind, captured_on=captured_on, treatment_plan_item_id=treatment_plan_item_id, provider_user_id=provider_user_id)
    if payload.treatment_plan_item_id is not None:
        valid_item = db.execute(text("""
            SELECT 1 FROM treatment_plan_items item
            JOIN treatment_plans plan ON plan.clinic_id = item.clinic_id AND plan.id = item.plan_id
            WHERE item.clinic_id = :clinic_id AND item.id = :item_id AND plan.patient_id = :patient_id
        """), {"clinic_id": session["clinic_id"], "item_id": payload.treatment_plan_item_id, "patient_id": patient_id}).scalar_one_or_none()
        if valid_item is None:
            raise _error("NOT_FOUND", "Treatment item not found for this patient.", status.HTTP_404_NOT_FOUND)
    if payload.provider_user_id is not None:
        # The (clinic_id, provider_user_id) FK already blocks cross-tenant ids, but
        # reject inactive/unknown users up front with a clean error instead of an
        # opaque integrity failure, and never attribute media to a disabled account.
        valid_provider = db.execute(text("""
            SELECT 1 FROM users
            WHERE clinic_id = :clinic_id AND id = :provider_user_id AND status = 'active'
        """), {"clinic_id": session["clinic_id"], "provider_user_id": payload.provider_user_id}).scalar_one_or_none()
        if valid_provider is None:
            raise _error("INVALID_INPUT", "The provider must be an active user of this clinic.", status.HTTP_400_BAD_REQUEST)
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
    content = await request.body()
    if content_type not in {"image/jpeg", "image/png", "image/webp"} or not content or len(content) > MAX_PATIENT_MEDIA_BYTES:
        raise _error("INVALID_UPLOAD", "Patient media must be a JPEG, PNG, or WebP image up to 8 MiB.", status.HTTP_400_BAD_REQUEST)
    try:
        validate_image_magic(content_type, content[:16])
    except ValueError as exc:
        raise _error("INVALID_UPLOAD", str(exc), status.HTTP_400_BAD_REQUEST) from exc
    media_id = uuid4()
    extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[content_type]
    storage_key = f"{session['clinic_id']}/{patient_id}/{media_id}{extension}"
    try:
        put_private_object(storage_key, content)
        row = db.execute(text("""
            INSERT INTO patient_media (id, clinic_id, patient_id, treatment_plan_item_id, provider_user_id, captured_on,
                media_kind, storage_key, original_filename, mime_type, size_bytes, content_sha256)
            VALUES (:id, :clinic_id, :patient_id, :item_id, COALESCE(:provider_user_id, :actor), COALESCE(:captured_on, CURRENT_DATE),
                :media_kind, :storage_key, :filename, :mime_type, :size_bytes, :sha256)
            RETURNING id, patient_id, treatment_plan_item_id, provider_user_id, captured_on, media_kind, mime_type,
                      size_bytes, scan_status, approval_status, approved_for_website, version, created_at
        """), {"id": media_id, "clinic_id": session["clinic_id"], "patient_id": patient_id, "item_id": payload.treatment_plan_item_id, "provider_user_id": payload.provider_user_id, "actor": session["user_id"], "captured_on": payload.captured_on, "media_kind": payload.media_kind, "storage_key": storage_key, "filename": f"patient-media{extension}", "mime_type": content_type, "size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}).mappings().one()
        db.execute(text("""
            INSERT INTO background_jobs (clinic_id, job_key, job_type, status)
            VALUES (:clinic_id, :job_key, 'patient_media_scan', 'queued')
            ON CONFLICT (clinic_id, job_key) DO NOTHING
        """), {"clinic_id": session["clinic_id"], "job_key": f"patient-media-scan:{media_id}"})
        record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="patient_media.upload", entity_type="patient_media", entity_id=media_id, outcome="pending_scan", request_id=UUID(request.state.request_id))
        db.commit()
    except Exception:
        db.rollback()
        delete_private_object(storage_key)
        raise
    return {"data": dict(row), "meta": {"request_id": request.state.request_id, "upload_status": "pending_scan"}}


@router.post("/{patient_id}/media/{media_id}/approve")
def media_approve(patient_id: UUID, media_id: UUID, payload: PatientMediaApproval, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "patient.media.approve", csrf_token)
    _require_patient(db, session, patient_id)
    media = _media_or_404(db, session, patient_id, media_id)
    if media["scan_status"] != "clean":
        raise _error("MEDIA_UNAVAILABLE", "Media must pass scanning before website approval.", status.HTTP_409_CONFLICT)
    consent = db.execute(text("""
        SELECT id FROM consent_records
        WHERE clinic_id = :clinic_id AND id = :consent_id AND patient_id = :patient_id AND status = 'granted' AND withdrawn_at IS NULL
    """), {"clinic_id": session["clinic_id"], "consent_id": payload.consent_record_id, "patient_id": patient_id}).scalar_one_or_none()
    if consent is None:
        raise _error("CONSENT_REQUIRED", "A current granted patient consent record is required.", status.HTTP_409_CONFLICT)
    row = db.execute(text("""
        UPDATE patient_media
        SET approval_status = 'approved', approved_for_website = true, consent_record_id = :consent_id,
            approved_by_user_id = :actor, approved_at = now(), version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND patient_id = :patient_id AND id = :media_id AND version = :expected_version AND archived_at IS NULL
        RETURNING id, patient_id, approval_status, approved_for_website, consent_record_id, approved_by_user_id, approved_at, version, updated_at
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "media_id": media_id, "expected_version": payload.expected_version, "consent_id": consent, "actor": session["user_id"]}).mappings().one_or_none()
    if row is None:
        raise _error("VERSION_CONFLICT", "The patient media changed before approval.", status.HTTP_409_CONFLICT)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="patient_media.approve_for_website", entity_type="patient_media", entity_id=media_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"consent_record_id": str(consent)})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.post("/{patient_id}/media/{media_id}/revoke")
def media_revoke(patient_id: UUID, media_id: UUID, payload: PatientMediaRevoke, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "patient.media.approve", csrf_token)
    _require_patient(db, session, patient_id)
    _media_or_404(db, session, patient_id, media_id)
    row = db.execute(text("""
        UPDATE patient_media
        SET approval_status = 'revoked', approved_for_website = false, approved_by_user_id = :actor, approved_at = now(), version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND patient_id = :patient_id AND id = :media_id AND version = :expected_version AND archived_at IS NULL
        RETURNING id, patient_id, approval_status, approved_for_website, version, updated_at
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "media_id": media_id, "expected_version": payload.expected_version, "actor": session["user_id"]}).mappings().one_or_none()
    if row is None:
        raise _error("VERSION_CONFLICT", "The patient media changed before revocation.", status.HTTP_409_CONFLICT)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="patient_media.revoke_website_approval", entity_type="patient_media", entity_id=media_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}

from __future__ import annotations

from datetime import datetime
import hashlib
import time
from uuid import UUID, uuid4

from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, Response, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.tenant import set_tenant_context
from app.modules.authorization.service import ForbiddenError, require_permission
from app.modules.crm.routes import _require_patient
from app.modules.files.schemas import DocumentAccess, DocumentCreate
from app.modules.files.service import MAX_PATIENT_DOCUMENT_BYTES, MetadataEncryptionError, create_access_token, display_original_filename, encrypt_original_filename, generic_filename, new_storage_key, validate_magic_bytes, validate_upload, verify_access_token
from app.modules.files.storage import delete_private_object, put_private_object
from app.modules.governance.limits import FeatureLimitExceeded, consume_feature_limit
from app.modules.audit.service import record_event
from app.modules.identity.routes import _error, _session_or_401, _validate_origin
from app.modules.identity.service import SessionError, verify_csrf
from app.core.security import decode_cursor, encode_cursor

router = APIRouter(prefix="/api/v1", tags=["files"])


def _authorized(db: Session, session_token: str | None, permission: str) -> dict:
    session = _session_or_401(db, session_token)
    if session["clinic_id"] is None:
        raise _error("FORBIDDEN", "A clinic context is required.", status.HTTP_403_FORBIDDEN)
    set_tenant_context(db, session["clinic_id"], session["user_id"])
    try:
        require_permission(db, session["user_id"], session["clinic_id"], permission)
    except ForbiddenError as exc:
        raise _error("FORBIDDEN", "You do not have permission for this operation.", status.HTTP_403_FORBIDDEN) from exc
    return session


def _write_authorized(db: Session, request: Request, session_token: str | None, permission: str, csrf_token: str | None) -> dict:
    _validate_origin(request)
    session = _authorized(db, session_token, permission)
    if not csrf_token:
        raise _error("CSRF_REQUIRED", "A CSRF token is required.", status.HTTP_403_FORBIDDEN)
    try:
        verify_csrf(session, csrf_token)
    except SessionError as exc:
        raise _error("CSRF_INVALID", "The CSRF token is invalid.", status.HTTP_403_FORBIDDEN) from exc
    return session


def _require_document(db: Session, session: dict, document_id: UUID) -> None:
    patient_id = db.execute(text("SELECT patient_id FROM patient_documents WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL"), {"clinic_id": session["clinic_id"], "id": document_id}).scalar_one_or_none()
    if patient_id is None:
        raise _error("NOT_FOUND", "Document not found.", status.HTTP_404_NOT_FOUND)
    _require_patient(db, session, patient_id)


def _document_public_data(row: object) -> dict:
    """Return decrypted metadata only after the caller has passed object scope."""
    data = dict(row)
    try:
        data["original_filename"] = display_original_filename(
            data.pop("original_filename_ciphertext", None),
            data.get("original_filename"),
            data["mime_type"],
        )
    except MetadataEncryptionError as exc:
        raise _error("DOCUMENT_UNAVAILABLE", "Document metadata is not currently available.", status.HTTP_404_NOT_FOUND) from exc
    return data


@router.get("/patients/{patient_id}/documents")
def document_list(patient_id: UUID, request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "patient.document.read")
    _require_patient(db, session, patient_id)
    cursor_values = decode_cursor(cursor, "patient-documents") if cursor else None
    if cursor and (cursor_values is None or cursor_values.get("patient_id") != str(patient_id)):
        raise _error("INVALID_INPUT", "The page cursor is invalid or does not match this patient.", status.HTTP_400_BAD_REQUEST)
    try:
        after_created_at = datetime.fromisoformat(cursor_values["created_at"]) if cursor_values else None
        after_id = UUID(cursor_values["id"]) if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT id, original_filename, original_filename_ciphertext, mime_type, size_bytes, scan_status, retention_class, created_at, version
        FROM patient_documents
        WHERE clinic_id = :clinic_id AND patient_id = :patient_id AND archived_at IS NULL
          AND (:after_created_at IS NULL OR created_at < :after_created_at OR (created_at = :after_created_at AND id < :after_id))
        ORDER BY created_at DESC, id DESC
        LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "after_created_at": after_created_at, "after_id": after_id, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_next and rows:
        next_cursor = encode_cursor("patient-documents", {"patient_id": str(patient_id), "created_at": rows[-1]["created_at"].isoformat(), "id": str(rows[-1]["id"])})
    db.commit()
    return {"data": [_document_public_data(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@router.post("/patients/{patient_id}/documents", status_code=status.HTTP_201_CREATED)
def document_create(patient_id: UUID, payload: DocumentCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "patient.document.write", csrf_token)
    _require_patient(db, session, patient_id)
    try:
        safe_name = validate_upload(payload.original_filename, payload.mime_type, payload.size_bytes, payload.content_sha256)
        filename_ciphertext = encrypt_original_filename(safe_name)
    except ValueError as exc:
        raise _error("INVALID_UPLOAD", str(exc), status.HTTP_400_BAD_REQUEST) from exc
    except MetadataEncryptionError as exc:
        raise _error("DOCUMENT_UPLOAD_UNAVAILABLE", "Private document uploads require configured metadata encryption.", status.HTTP_503_SERVICE_UNAVAILABLE) from exc
    try:
        consume_feature_limit(db, session["clinic_id"], "patient_document_bytes", payload.size_bytes)
    except FeatureLimitExceeded as exc:
        db.rollback()
        raise _error("FEATURE_LIMIT_EXCEEDED", "The clinic document-storage limit has been reached.", status.HTTP_409_CONFLICT) from exc
    document_id = uuid4()
    storage_key = new_storage_key(str(session["clinic_id"]), str(patient_id), str(document_id), safe_name)
    try:
        row = db.execute(text("""
            INSERT INTO patient_documents (id, clinic_id, patient_id, uploaded_by_user_id, storage_key, original_filename, original_filename_ciphertext, mime_type, size_bytes, content_sha256)
            VALUES (:id, :clinic_id, :patient_id, :user_id, :storage_key, :legacy_filename, :filename_ciphertext, :mime_type, :size_bytes, :sha256)
            RETURNING id, original_filename, original_filename_ciphertext, mime_type, size_bytes, scan_status, created_at, version
        """), {"id": document_id, "clinic_id": session["clinic_id"], "patient_id": patient_id, "user_id": session["user_id"], "storage_key": storage_key, "legacy_filename": generic_filename(payload.mime_type), "filename_ciphertext": filename_ciphertext, "mime_type": payload.mime_type, "size_bytes": payload.size_bytes, "sha256": payload.content_sha256.lower()}).mappings().one()
    except IntegrityError as exc:
        db.rollback()
        raise _error("NOT_FOUND", "Patient not found.", status.HTTP_404_NOT_FOUND) from exc
    db.execute(text("""
        INSERT INTO background_jobs (clinic_id, job_key, job_type, status)
        VALUES (:clinic_id, :job_key, 'document_scan', 'queued')
        ON CONFLICT (clinic_id, job_key) DO NOTHING
    """), {"clinic_id": session["clinic_id"], "job_key": f"document-scan:{document_id}"})
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="document.upload", entity_type="patient_document", entity_id=document_id, outcome="pending_scan", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": _document_public_data(row), "meta": {"request_id": request.state.request_id, "upload_status": "pending_scan"}}


@router.post("/patients/{patient_id}/documents/upload", status_code=status.HTTP_201_CREATED)
async def document_upload(patient_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"), original_filename: str | None = Header(default=None, alias="X-Original-Filename")) -> dict:
    """Accept a raw private object and place it in pending_scan atomically with metadata."""
    session = _write_authorized(db, request, session_token, "patient.document.write", csrf_token)
    _require_patient(db, session, patient_id)
    if not original_filename:
        raise _error("INVALID_UPLOAD", "X-Original-Filename is required.", status.HTTP_400_BAD_REQUEST)
    mime_type = request.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
    content = await request.body()
    if len(content) > MAX_PATIENT_DOCUMENT_BYTES:
        raise _error("FILE_TOO_LARGE", "The document exceeds the 20 MiB limit.", status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    content_sha256 = hashlib.sha256(content).hexdigest()
    try:
        safe_name = validate_upload(original_filename, mime_type, len(content), content_sha256)
        validate_magic_bytes(mime_type, content[:16])
        filename_ciphertext = encrypt_original_filename(safe_name)
    except ValueError as exc:
        raise _error("INVALID_UPLOAD", str(exc), status.HTTP_400_BAD_REQUEST) from exc
    except MetadataEncryptionError as exc:
        raise _error("DOCUMENT_UPLOAD_UNAVAILABLE", "Private document uploads require configured metadata encryption.", status.HTTP_503_SERVICE_UNAVAILABLE) from exc
    try:
        consume_feature_limit(db, session["clinic_id"], "patient_document_bytes", len(content))
    except FeatureLimitExceeded as exc:
        db.rollback()
        raise _error("FEATURE_LIMIT_EXCEEDED", "The clinic document-storage limit has been reached.", status.HTTP_409_CONFLICT) from exc
    document_id = uuid4()
    storage_key = new_storage_key(str(session["clinic_id"]), str(patient_id), str(document_id), safe_name)
    try:
        put_private_object(storage_key, content)
        row = db.execute(text("""
            INSERT INTO patient_documents (id, clinic_id, patient_id, uploaded_by_user_id, storage_key, original_filename, original_filename_ciphertext, mime_type, size_bytes, content_sha256)
            VALUES (:id, :clinic_id, :patient_id, :user_id, :storage_key, :legacy_filename, :filename_ciphertext, :mime_type, :size_bytes, :sha256)
            RETURNING id, original_filename, original_filename_ciphertext, mime_type, size_bytes, scan_status, created_at, version
        """), {"id": document_id, "clinic_id": session["clinic_id"], "patient_id": patient_id, "user_id": session["user_id"], "storage_key": storage_key, "legacy_filename": generic_filename(mime_type), "filename_ciphertext": filename_ciphertext, "mime_type": mime_type, "size_bytes": len(content), "sha256": content_sha256}).mappings().one()
        db.execute(text("""
            INSERT INTO background_jobs (clinic_id, job_key, job_type, status)
            VALUES (:clinic_id, :job_key, 'document_scan', 'queued')
            ON CONFLICT (clinic_id, job_key) DO NOTHING
        """), {"clinic_id": session["clinic_id"], "job_key": f"document-scan:{document_id}"})
        record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="document.upload", entity_type="patient_document", entity_id=document_id, outcome="pending_scan", request_id=UUID(request.state.request_id))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        delete_private_object(storage_key)
        raise _error("NOT_FOUND", "Patient not found.", status.HTTP_404_NOT_FOUND) from exc
    except Exception:
        db.rollback()
        delete_private_object(storage_key)
        raise
    return {"data": _document_public_data(row), "meta": {"request_id": request.state.request_id, "upload_status": "pending_scan"}}


@router.get("/documents/{document_id}/scan-status")
def document_scan_status(document_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "patient.document.read")
    _require_document(db, session, document_id)
    document = db.execute(text("SELECT id, scan_status, scan_failure_reason, updated_at FROM patient_documents WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL"), {"clinic_id": session["clinic_id"], "id": document_id}).mappings().one_or_none()
    if document is None:
        raise _error("NOT_FOUND", "Document not found.", status.HTTP_404_NOT_FOUND)
    events = db.execute(text("SELECT engine, signature_version, outcome, failure_reason, scanned_at FROM file_scan_events WHERE clinic_id = :clinic_id AND document_id = :id ORDER BY scanned_at DESC, id"), {"clinic_id": session["clinic_id"], "id": document_id}).mappings().all()
    db.commit()
    return {"data": {**dict(document), "events": [dict(event) for event in events]}, "meta": {"request_id": request.state.request_id}}


@router.post("/documents/{document_id}/signed-access")
def document_signed_access(document_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "patient.document.read")
    _require_document(db, session, document_id)
    row = db.execute(text("SELECT id, scan_status FROM patient_documents WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL"), {"clinic_id": session["clinic_id"], "id": document_id}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Document not found.", status.HTTP_404_NOT_FOUND)
    if row["scan_status"] != "clean":
        raise _error("DOCUMENT_UNAVAILABLE", "The document is not available until scanning succeeds.", status.HTTP_409_CONFLICT)
    expires_at = int(time.time()) + 60
    access = DocumentAccess(document_id=document_id, expires_at=expires_at, access_token=create_access_token(str(document_id), str(session["user_id"]), expires_at))
    db.execute(text("INSERT INTO document_access_events (clinic_id, document_id, user_id, action, request_id) VALUES (:clinic_id, :document_id, :user_id, 'signed_access_issued', :request_id)"), {"clinic_id": session["clinic_id"], "document_id": document_id, "user_id": session["user_id"], "request_id": UUID(request.state.request_id)})
    db.commit()
    return {"data": access.model_dump(), "meta": {"request_id": request.state.request_id, "expires_in_seconds": 60}}


@router.get("/documents/{document_id}/download")
def document_download(document_id: UUID, request: Request, access_token: str | None = Header(default=None, alias="X-Document-Access-Token"), access_expires: int | None = Header(default=None, alias="X-Document-Expires"), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> Response:
    """Serve a clean private object through a short-lived, user-bound proxy."""
    session = _authorized(db, session_token, "patient.document.read")
    _require_document(db, session, document_id)
    row = db.execute(text("SELECT id, storage_key, original_filename, original_filename_ciphertext, mime_type, scan_status FROM patient_documents WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL"), {"clinic_id": session["clinic_id"], "id": document_id}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Document not found.", status.HTTP_404_NOT_FOUND)
    if row["scan_status"] != "clean" or not access_token or access_expires is None or access_expires <= int(time.time()) or not verify_access_token(access_token, str(document_id), str(session["user_id"]), access_expires):
        raise _error("DOCUMENT_UNAVAILABLE", "The document access token is invalid or expired.", status.HTTP_404_NOT_FOUND)
    try:
        from app.modules.files.storage import read_private_object

        content = read_private_object(row["storage_key"])
    except (FileNotFoundError, ValueError) as exc:
        raise _error("DOCUMENT_UNAVAILABLE", "The document is not currently available.", status.HTTP_404_NOT_FOUND) from exc
    db.execute(text("INSERT INTO document_access_events (clinic_id, document_id, user_id, action, request_id) VALUES (:clinic_id, :document_id, :user_id, 'downloaded', :request_id)"), {"clinic_id": session["clinic_id"], "document_id": document_id, "user_id": session["user_id"], "request_id": UUID(request.state.request_id)})
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="document.download", entity_type="patient_document", entity_id=document_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    safe_filename = _document_public_data(row)["original_filename"].replace("\r", "").replace("\n", "").replace('"', "")
    return Response(content=content, media_type=row["mime_type"], headers={"Content-Disposition": f'attachment; filename="{safe_filename}"', "Cache-Control": "private, no-store"})


@router.post("/documents/{document_id}/archive")
def document_archive(document_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "patient.document.delete", csrf_token)
    _require_document(db, session, document_id)
    row = db.execute(text("UPDATE patient_documents SET archived_at = now(), updated_at = now(), version = version + 1 WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL RETURNING id, archived_at, version"), {"clinic_id": session["clinic_id"], "id": document_id}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Document not found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="document.archive", entity_type="patient_document", entity_id=document_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}

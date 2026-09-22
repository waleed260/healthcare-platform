from __future__ import annotations

from datetime import datetime, timedelta, timezone
import time
import secrets
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, Response, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.tenant import set_tenant_context
from app.modules.audit.service import record_event
from app.modules.authorization.service import ForbiddenError, require_permission
from app.modules.governance.schemas import ExportJobCreate, PrivacyIdentityVerify, PrivacyRequestCreate, PrivacyRequestResolve, SubscriptionUpdate, SupportAccessCreate
from app.modules.identity.routes import _error, _session_or_401, _validate_origin
from app.modules.identity.service import SessionError, verify_csrf
from app.modules.files.storage import read_private_object
from app.core.security import decode_cursor, encode_cursor, hash_token
from app.modules.crm.routes import _patient_scope_sql

router = APIRouter(prefix="/api/v1/governance", tags=["governance"])


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


def _patient_visible_to_user(db: Session, session: dict, patient_id: UUID) -> bool:
    return bool(db.execute(text("""
        SELECT EXISTS (
            SELECT 1
            FROM patients p
            WHERE p.clinic_id = :clinic_id AND p.id = :patient_id AND p.archived_at IS NULL
              {_patient_scope_sql('p')}
        )
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "patient_id": patient_id}).scalar_one())


@router.get("/subscription")
def subscription_get(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "admin.plan.manage")
    row = db.execute(text("""
        SELECT cs.id, p.code, p.name, cs.status, cs.starts_at, cs.ends_at
        FROM clinic_subscriptions cs JOIN plans p ON p.id = cs.plan_id
        WHERE cs.clinic_id = :clinic_id ORDER BY cs.created_at DESC LIMIT 1
    """), {"clinic_id": session["clinic_id"]}).mappings().one_or_none()
    db.commit()
    return {"data": dict(row) if row else None, "meta": {"request_id": request.state.request_id}}


@router.put("/subscription")
def subscription_update(payload: SubscriptionUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "admin.plan.manage", csrf_token)
    row = db.execute(text("SELECT id FROM plans WHERE code = :code AND active"), {"code": payload.plan_code}).scalar_one_or_none()
    if row is None:
        raise _error("INVALID_INPUT", "The requested plan is not active.", status.HTTP_400_BAD_REQUEST)
    result = db.execute(text("""
        INSERT INTO clinic_subscriptions (clinic_id, plan_id, status)
        VALUES (:clinic_id, :plan_id, :status)
        RETURNING id, status, starts_at, ends_at
    """), {"clinic_id": session["clinic_id"], "plan_id": row, "status": payload.status}).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="subscription.update", entity_type="clinic_subscription", entity_id=result["id"], outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(result), "meta": {"request_id": request.state.request_id}}


@router.post("/support-access", status_code=status.HTTP_201_CREATED)
def support_access_create(payload: SupportAccessCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "admin.support.access", csrf_token)
    approved_by = payload.approved_by_user_id or session["user_id"]
    if approved_by == session["user_id"]:
        raise _error("APPROVAL_REQUIRED", "Support access requires a separate approver.", status.HTTP_403_FORBIDDEN)
    valid_approver = db.execute(text("""
        SELECT 1
        FROM users u
        JOIN user_roles ur ON ur.clinic_id = u.clinic_id AND ur.user_id = u.id
        JOIN role_permissions rp ON rp.role_id = ur.role_id
        WHERE u.clinic_id = :clinic_id AND u.id = :user_id
          AND u.status = 'active' AND u.archived_at IS NULL
          AND rp.permission_code = 'admin.support.access'
    """), {"clinic_id": session["clinic_id"], "user_id": approved_by}).scalar_one_or_none()
    if valid_approver is None:
        raise _error("APPROVAL_REQUIRED", "The approver is not authorized for support access.", status.HTTP_403_FORBIDDEN)
    result = db.execute(text("""
        INSERT INTO support_access_sessions (clinic_id, requested_by_user_id, approved_by_user_id, reason, permissions, starts_at, expires_at)
        VALUES (:clinic_id, :requester, :approver, :reason, CAST(:permissions AS jsonb), now(), now() + (:minutes * interval '1 minute'))
        RETURNING id, starts_at, expires_at, permissions
    """), {"clinic_id": session["clinic_id"], "requester": session["user_id"], "approver": approved_by, "reason": payload.reason, "permissions": __import__("json").dumps(payload.permissions), "minutes": payload.expires_in_minutes}).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], support_session_id=result["id"], action="support_access.create", entity_type="support_access_session", entity_id=result["id"], outcome="success", request_id=UUID(request.state.request_id), metadata={"expires_in_minutes": payload.expires_in_minutes})
    db.commit()
    return {"data": dict(result), "meta": {"request_id": request.state.request_id}}


@router.post("/support-access/{access_id}/revoke")
def support_access_revoke(access_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "admin.support.access", csrf_token)
    result = db.execute(text("UPDATE support_access_sessions SET revoked_at = now() WHERE clinic_id = :clinic_id AND id = :id AND revoked_at IS NULL RETURNING id, revoked_at"), {"clinic_id": session["clinic_id"], "id": access_id}).mappings().one_or_none()
    if result is None:
        raise _error("NOT_FOUND", "Support access session not found or already revoked.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], support_session_id=access_id, action="support_access.revoke", entity_type="support_access_session", entity_id=access_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(result), "meta": {"request_id": request.state.request_id}}


@router.get("/privacy-requests")
def privacy_request_list(request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "patient.read")
    cursor_values = decode_cursor(cursor, "privacy-requests") if cursor else None
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    try:
        after_requested_at = datetime.fromisoformat(cursor_values["requested_at"]) if cursor_values else None
        after_id = UUID(cursor_values["id"]) if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT id, patient_id, request_type, status, reason, requested_at, resolved_at, resolution_note
        FROM privacy_requests
        WHERE clinic_id = :clinic_id
          AND EXISTS (
            SELECT 1 FROM patients p
            WHERE p.clinic_id = privacy_requests.clinic_id AND p.id = privacy_requests.patient_id AND p.archived_at IS NULL
              AND (
                NOT EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id)
                OR EXISTS (
                    SELECT 1 FROM appointments a
                    JOIN user_branch_scopes s ON s.clinic_id = a.clinic_id AND s.branch_id = a.branch_id
                    WHERE a.clinic_id = :clinic_id AND a.patient_id = privacy_requests.patient_id AND a.archived_at IS NULL AND s.user_id = :user_id
                )
              )
          )
          AND (:after_requested_at IS NULL OR requested_at < :after_requested_at OR (requested_at = :after_requested_at AND id < :after_id))
        ORDER BY requested_at DESC, id DESC
        LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "after_requested_at": after_requested_at, "after_id": after_id, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor("privacy-requests", {"requested_at": rows[-1]["requested_at"].isoformat(), "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@router.get("/audit")
def audit_search(request: Request, action: str | None = Query(default=None, max_length=120), cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "audit.read")
    cursor_values = decode_cursor(cursor, "audit-search") if cursor else None
    if cursor and (cursor_values is None or cursor_values.get("action") != (action or "")):
        raise _error("INVALID_INPUT", "The page cursor is invalid or does not match this filter.", status.HTTP_400_BAD_REQUEST)
    try:
        after_created_at = datetime.fromisoformat(cursor_values["created_at"]) if cursor_values else None
        after_id = UUID(cursor_values["id"]) if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT id, actor_user_id, action, entity_type, entity_id, outcome, request_id, created_at
        FROM audit_events
        WHERE clinic_id = :clinic_id AND (:action IS NULL OR action = :action)
          AND (:after_created_at IS NULL OR created_at < :after_created_at OR (created_at = :after_created_at AND id < :after_id))
        ORDER BY created_at DESC, id DESC
        LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "action": action, "after_created_at": after_created_at, "after_id": after_id, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor("audit-search", {"action": action or "", "created_at": rows[-1]["created_at"].isoformat(), "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@router.get("/exports")
def export_list(request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "patient.export")
    cursor_values = decode_cursor(cursor, "exports") if cursor else None
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    try:
        after_created_at = datetime.fromisoformat(cursor_values["created_at"]) if cursor_values else None
        after_id = UUID(cursor_values["id"]) if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT id, export_type, status, patient_id, privacy_request_id, created_at, completed_at, expires_at
        FROM export_jobs
        WHERE clinic_id = :clinic_id
          AND (
            patient_id IS NULL
            OR EXISTS (
                SELECT 1
                FROM patients p
                WHERE p.clinic_id = export_jobs.clinic_id AND p.id = export_jobs.patient_id AND p.archived_at IS NULL
                  AND (
                    NOT EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id)
                    OR EXISTS (
                        SELECT 1 FROM appointments a
                        JOIN user_branch_scopes s ON s.clinic_id = a.clinic_id AND s.branch_id = a.branch_id
                        WHERE a.clinic_id = :clinic_id AND a.patient_id = export_jobs.patient_id AND a.archived_at IS NULL AND s.user_id = :user_id
                    )
                  )
            )
          )
          AND (:after_created_at IS NULL OR created_at < :after_created_at OR (created_at = :after_created_at AND id < :after_id))
        ORDER BY created_at DESC, id DESC
        LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "after_created_at": after_created_at, "after_id": after_id, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor("exports", {"created_at": rows[-1]["created_at"].isoformat(), "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@router.post("/exports", status_code=status.HTTP_202_ACCEPTED)
def export_create(payload: ExportJobCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "patient.export", csrf_token)
    if payload.export_type == "patient_access" and payload.patient_id is None:
        raise _error("INVALID_INPUT", "A patient is required for a patient access export.", status.HTTP_400_BAD_REQUEST)
    if payload.patient_id is not None and not _patient_visible_to_user(db, session, payload.patient_id):
        raise _error("NOT_FOUND", "The requested export target was not found.", status.HTTP_404_NOT_FOUND)
    try:
        row = db.execute(text("""
            INSERT INTO export_jobs (clinic_id, requested_by_user_id, patient_id, privacy_request_id, export_type)
            VALUES (:clinic_id, :user_id, :patient_id, :privacy_request_id, :export_type)
            RETURNING id, export_type, status, patient_id, privacy_request_id, created_at
        """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "patient_id": payload.patient_id, "privacy_request_id": payload.privacy_request_id, "export_type": payload.export_type}).mappings().one()
        db.execute(text("INSERT INTO background_jobs (clinic_id, job_key, job_type) VALUES (:clinic_id, :job_key, 'export') ON CONFLICT (clinic_id, job_key) DO NOTHING"), {"clinic_id": session["clinic_id"], "job_key": f"export:{row['id']}"})
    except IntegrityError as exc:
        db.rollback()
        raise _error("NOT_FOUND", "The requested export target was not found.", status.HTTP_404_NOT_FOUND) from exc
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="export.create", entity_type="export_job", entity_id=row["id"], outcome="queued", request_id=UUID(request.state.request_id), metadata={"export_type": payload.export_type})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.post("/exports/{export_id}/signed-access")
def export_signed_access(export_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "patient.export", csrf_token)
    export = db.execute(text("SELECT id, status, expires_at FROM export_jobs WHERE clinic_id = :clinic_id AND id = :id"), {"clinic_id": session["clinic_id"], "id": export_id}).mappings().one_or_none()
    if export is None:
        raise _error("NOT_FOUND", "Export job not found.", status.HTTP_404_NOT_FOUND)
    if export["status"] != "completed" or export["expires_at"] is None or export["expires_at"].timestamp() <= time.time():
        raise _error("EXPORT_UNAVAILABLE", "The export is not ready or has expired.", status.HTTP_409_CONFLICT)
    token = secrets.token_urlsafe(32)
    expires_at = min(export["expires_at"], datetime.now(timezone.utc) + timedelta(seconds=60))
    db.execute(text("UPDATE export_jobs SET download_token_hash = :token_hash WHERE clinic_id = :clinic_id AND id = :id"), {"clinic_id": session["clinic_id"], "id": export_id, "token_hash": hash_token(f"export:{export_id}:{session['user_id']}:{token}")})
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="export.signed_access", entity_type="export_job", entity_id=export_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"expires_in_seconds": 60})
    db.commit()
    return {"data": {"export_id": export_id, "access_token": token, "expires_at": expires_at}, "meta": {"request_id": request.state.request_id, "token_returned_once": True}}


@router.get("/exports/{export_id}/download")
def export_download(export_id: UUID, request: Request, access_token: str | None = Header(default=None, alias="X-Export-Access-Token"), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> Response:
    session = _authorized(db, session_token, "patient.export")
    export = db.execute(text("SELECT storage_key, download_token_hash, expires_at FROM export_jobs WHERE clinic_id = :clinic_id AND id = :id AND status = 'completed'"), {"clinic_id": session["clinic_id"], "id": export_id}).mappings().one_or_none()
    expected_hash = hash_token(f"export:{export_id}:{session['user_id']}:{access_token}") if access_token else ""
    if export is None or not access_token or not export["download_token_hash"] or export["expires_at"] is None or export["expires_at"].timestamp() <= time.time() or expected_hash != export["download_token_hash"].strip():
        raise _error("EXPORT_UNAVAILABLE", "The export access token is invalid or expired.", status.HTTP_404_NOT_FOUND)
    try:
        content = read_private_object(export["storage_key"])
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise _error("EXPORT_UNAVAILABLE", "The export is not currently available.", status.HTTP_404_NOT_FOUND) from exc
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="export.download", entity_type="export_job", entity_id=export_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return Response(content=content, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="export-{export_id}.json"', "Cache-Control": "private, no-store"})


@router.post("/patients/{patient_id}/privacy-requests", status_code=status.HTTP_201_CREATED)
def privacy_request_create(patient_id: UUID, payload: PrivacyRequestCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "patient.update", csrf_token)
    if not _patient_visible_to_user(db, session, patient_id):
        raise _error("NOT_FOUND", "Patient not found.", status.HTTP_404_NOT_FOUND)
    try:
        row = db.execute(text("""
            INSERT INTO privacy_requests (clinic_id, patient_id, request_type, reason, requested_by_user_id)
            VALUES (:clinic_id, :patient_id, :request_type, :reason, :user_id)
            RETURNING id, patient_id, request_type, status, requested_at, identity_verified_at
        """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "request_type": payload.request_type, "reason": payload.reason, "user_id": session["user_id"]}).mappings().one()
    except IntegrityError as exc:
        db.rollback()
        raise _error("NOT_FOUND", "Patient not found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="privacy_request.create", entity_type="privacy_request", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id), metadata={"request_type": payload.request_type})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.post("/privacy-requests/{request_id}/verify-identity")
def privacy_request_verify_identity(request_id: UUID, payload: PrivacyIdentityVerify, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "admin.clinic.manage", csrf_token)
    patient_id = db.execute(text("SELECT patient_id FROM privacy_requests WHERE clinic_id = :clinic_id AND id = :id"), {"clinic_id": session["clinic_id"], "id": request_id}).scalar_one_or_none()
    if patient_id is None or not _patient_visible_to_user(db, session, patient_id):
        raise _error("NOT_FOUND", "Privacy request not found.", status.HTTP_404_NOT_FOUND)
    result = db.execute(text("""
        UPDATE privacy_requests
        SET identity_verified_at = now(), identity_verified_by_user_id = :user_id,
            identity_verification_evidence = :evidence
        WHERE clinic_id = :clinic_id AND id = :id AND identity_verified_at IS NULL
        RETURNING id, identity_verified_at, identity_verified_by_user_id, identity_verification_evidence
    """), {"clinic_id": session["clinic_id"], "id": request_id, "user_id": session["user_id"], "evidence": payload.evidence_note.strip()}).mappings().one_or_none()
    if result is None:
        raise _error("NOT_FOUND", "Privacy request not found or already verified.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="privacy_request.identity_verify", entity_type="privacy_request", entity_id=request_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"evidence_recorded": True})
    db.commit()
    return {"data": dict(result), "meta": {"request_id": request.state.request_id}}


@router.post("/privacy-requests/{request_id}/execute", status_code=status.HTTP_202_ACCEPTED)
def privacy_request_execute(request_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "admin.clinic.manage", csrf_token)
    privacy = db.execute(text("""
        SELECT id, patient_id, request_type, status, identity_verified_at
        FROM privacy_requests WHERE clinic_id = :clinic_id AND id = :id FOR UPDATE
    """), {"clinic_id": session["clinic_id"], "id": request_id}).mappings().one_or_none()
    if privacy is None:
        raise _error("NOT_FOUND", "Privacy request not found.", status.HTTP_404_NOT_FOUND)
    if not _patient_visible_to_user(db, session, privacy["patient_id"]):
        raise _error("NOT_FOUND", "Privacy request not found.", status.HTTP_404_NOT_FOUND)
    if privacy["status"] != "approved":
        raise _error("INVALID_TRANSITION", "Only approved privacy requests can be executed.", status.HTTP_409_CONFLICT)
    if privacy["identity_verified_at"] is None:
        raise _error("IDENTITY_VERIFICATION_REQUIRED", "Verify the requester before execution.", status.HTTP_409_CONFLICT)
    if privacy["request_type"] == "access":
        export = db.execute(text("""
            INSERT INTO export_jobs (clinic_id, requested_by_user_id, patient_id, privacy_request_id, export_type)
            VALUES (:clinic_id, :user_id, :patient_id, :request_id, 'patient_access')
            RETURNING id, status, created_at
        """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "patient_id": privacy["patient_id"], "request_id": request_id}).mappings().one()
        db.execute(text("""
            INSERT INTO background_jobs (clinic_id, job_key, job_type, status)
            VALUES (:clinic_id, :job_key, 'export', 'queued')
            ON CONFLICT (clinic_id, job_key) DO NOTHING
        """), {"clinic_id": session["clinic_id"], "job_key": f"export:{export['id']}"})
        db.execute(text("UPDATE privacy_requests SET status = 'in_review', legal_hold_checked_at = now() WHERE clinic_id = :clinic_id AND id = :id"), {"clinic_id": session["clinic_id"], "id": request_id})
        record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="privacy_request.export_queued", entity_type="privacy_request", entity_id=request_id, outcome="success", request_id=UUID(request.state.request_id))
        db.commit()
        return {"data": {"privacy_request_id": request_id, "export_job_id": export["id"], "status": "in_review"}, "meta": {"request_id": request.state.request_id}}
    legal_hold = db.execute(text("SELECT 1 FROM patient_documents WHERE clinic_id = :clinic_id AND patient_id = :patient_id AND legal_hold AND archived_at IS NULL LIMIT 1"), {"clinic_id": session["clinic_id"], "patient_id": privacy["patient_id"]}).scalar_one_or_none()
    if legal_hold is not None:
        raise _error("LEGAL_HOLD", "The erasure request is blocked by a legal hold.", status.HTTP_409_CONFLICT)
    db.execute(text("DELETE FROM patient_contacts WHERE clinic_id = :clinic_id AND patient_id = :patient_id"), {"clinic_id": session["clinic_id"], "patient_id": privacy["patient_id"]})
    db.execute(text("DELETE FROM patient_notes WHERE clinic_id = :clinic_id AND patient_id = :patient_id"), {"clinic_id": session["clinic_id"], "patient_id": privacy["patient_id"]})
    db.execute(text("UPDATE patient_documents SET archived_at = now(), updated_at = now(), version = version + 1 WHERE clinic_id = :clinic_id AND patient_id = :patient_id AND NOT legal_hold"), {"clinic_id": session["clinic_id"], "patient_id": privacy["patient_id"]})
    db.execute(text("""
        UPDATE patients SET full_name = 'Redacted patient', normalized_email = NULL,
            normalized_phone = NULL, date_of_birth = NULL, status = 'erased',
            archived_at = now(), version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :patient_id
    """), {"clinic_id": session["clinic_id"], "patient_id": privacy["patient_id"]})
    db.execute(text("UPDATE privacy_requests SET status = 'completed', legal_hold_checked_at = now(), resolved_by_user_id = :user_id, resolved_at = now(), completion_evidence = 'Eligible direct identifiers pseudonymized; dependent records archived or removed.' WHERE clinic_id = :clinic_id AND id = :id"), {"clinic_id": session["clinic_id"], "id": request_id, "user_id": session["user_id"]})
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="privacy_request.erasure_complete", entity_type="privacy_request", entity_id=request_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"non_identifying_completion": True})
    db.commit()
    return {"data": {"privacy_request_id": request_id, "status": "completed"}, "meta": {"request_id": request.state.request_id}}


@router.post("/privacy-requests/{request_id}/resolve")
def privacy_request_resolve(request_id: UUID, payload: PrivacyRequestResolve, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "admin.clinic.manage", csrf_token)
    patient_id = db.execute(text("SELECT patient_id FROM privacy_requests WHERE clinic_id = :clinic_id AND id = :id"), {"clinic_id": session["clinic_id"], "id": request_id}).scalar_one_or_none()
    if patient_id is None or not _patient_visible_to_user(db, session, patient_id):
        raise _error("NOT_FOUND", "Privacy request not found.", status.HTTP_404_NOT_FOUND)
    result = db.execute(text("""
        UPDATE privacy_requests SET status = :status, resolved_by_user_id = :user_id,
            resolved_at = CASE WHEN :status IN ('rejected', 'completed') THEN now() ELSE NULL END,
            resolution_note = :note
        WHERE clinic_id = :clinic_id AND id = :id AND status = :expected_status
        RETURNING id, status, resolved_at, resolution_note
    """), {"clinic_id": session["clinic_id"], "id": request_id, "status": payload.status, "expected_status": payload.expected_status, "user_id": session["user_id"], "note": payload.resolution_note}).mappings().one_or_none()
    if result is None:
        raise _error("VERSION_CONFLICT", "The privacy request changed before resolution.", status.HTTP_409_CONFLICT)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="privacy_request.resolve", entity_type="privacy_request", entity_id=request_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"status": payload.status})
    db.commit()
    return {"data": dict(result), "meta": {"request_id": request.state.request_id}}

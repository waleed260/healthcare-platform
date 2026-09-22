from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, Response, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.tenant import set_platform_context, set_tenant_context
from app.modules.audit.service import record_event
from app.modules.governance.schemas import AnnouncementCreate, PlanCreate, PlanLimitUpdate, RetentionPolicyAssign, RetentionPolicyCreate
from app.modules.identity.routes import _error, _session_or_401, _set_session_cookies, _validate_origin
from app.modules.identity.service import SessionError, rotate_session, verify_csrf
from app.core.observability import request_metrics
from app.db.session import engine
from app.core.security import decode_cursor, encode_cursor

router = APIRouter(prefix="/api/v1/admin", tags=["platform-admin"])


def _platform(db: Session, session_token: str | None) -> dict:
    session = _session_or_401(db, session_token)
    if session["clinic_id"] is not None or not db.execute(text("SELECT is_platform_admin FROM users WHERE id = :id AND status = 'active'"), {"id": session["user_id"]}).scalar_one_or_none():
        raise _error("FORBIDDEN", "Platform administrator access is required.", status.HTTP_403_FORBIDDEN)
    set_platform_context(db, session["user_id"])
    return session


def _write(db: Session, request: Request, session_token: str | None, csrf_token: str | None) -> dict:
    _validate_origin(request)
    session = _platform(db, session_token)
    if not csrf_token:
        raise _error("CSRF_REQUIRED", "A CSRF token is required.", status.HTTP_403_FORBIDDEN)
    try:
        verify_csrf(session, csrf_token)
    except SessionError as exc:
        raise _error("CSRF_INVALID", "The CSRF token is invalid.", status.HTTP_403_FORBIDDEN) from exc
    return session


@router.post("/support-access/{access_id}/activate")
def support_access_activate(access_id: UUID, response: Response, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write(db, request, session_token, csrf_token)
    access = db.execute(text("""
        SELECT id, clinic_id, permissions, starts_at, expires_at
        FROM support_access_sessions
        WHERE id = :id AND revoked_at IS NULL AND starts_at <= now() AND expires_at > now()
    """), {"id": access_id}).mappings().one_or_none()
    if access is None:
        raise _error("SUPPORT_ACCESS_EXPIRED", "The support session is missing, expired, or revoked.", status.HTTP_409_CONFLICT)
    rotation = rotate_session(db, session, support_access_id=access_id)
    set_tenant_context(db, access["clinic_id"], session["user_id"])
    record_event(db, clinic_id=access["clinic_id"], actor_user_id=session["user_id"], support_session_id=access_id, action="support_access.activate", entity_type="support_access_session", entity_id=access_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    _set_session_cookies(response, rotation.session_token, rotation.csrf_token, clinic_id=None)
    return {"data": {"clinic_id": access["clinic_id"], "support_access_id": access_id, "permissions": access["permissions"], "expires_at": access["expires_at"]}, "meta": {"request_id": request.state.request_id}}


@router.post("/support-access/{access_id}/exit")
def support_access_exit(access_id: UUID, response: Response, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    _validate_origin(request)
    session = _session_or_401(db, session_token)
    if not session.get("is_platform_admin") or session.get("support_access_id") != access_id:
        raise _error("FORBIDDEN", "An active support context is required.", status.HTTP_403_FORBIDDEN)
    if not csrf_token:
        raise _error("CSRF_REQUIRED", "A CSRF token is required.", status.HTTP_403_FORBIDDEN)
    try:
        verify_csrf(session, csrf_token)
    except SessionError as exc:
        raise _error("CSRF_INVALID", "The CSRF token is invalid.", status.HTTP_403_FORBIDDEN) from exc
    rotation = rotate_session(db, session, clear_support_context=True)
    set_tenant_context(db, session["clinic_id"], session["user_id"])
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], support_session_id=access_id, action="support_access.exit", entity_type="support_access_session", entity_id=access_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    _set_session_cookies(response, rotation.session_token, rotation.csrf_token, clinic_id=None)
    return {"data": {"support_access_id": access_id, "exited": True}, "meta": {"request_id": request.state.request_id}}


@router.get("/plans")
def plans_list(request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    _platform(db, session_token)
    cursor_values = decode_cursor(cursor, "admin-plans") if cursor else None
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    try:
        after_code = cursor_values["code"] if cursor_values else None
        after_id = UUID(cursor_values["id"]) if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT p.id, p.code, p.name, p.active, p.created_at,
               COALESCE(jsonb_object_agg(fl.feature_code, jsonb_build_object('limit_value', fl.limit_value, 'enabled', fl.enabled)) FILTER (WHERE fl.feature_code IS NOT NULL), '{}'::jsonb) AS limits
        FROM plans p LEFT JOIN feature_limits fl ON fl.plan_id = p.id
        WHERE (:after_code IS NULL OR p.code > :after_code OR (p.code = :after_code AND p.id > :after_id))
        GROUP BY p.id ORDER BY p.code, p.id
        LIMIT :page_size
    """), {"after_code": after_code, "after_id": after_id, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor("admin-plans", {"code": rows[-1]["code"], "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@router.post("/plans", status_code=status.HTTP_201_CREATED)
def plan_create(payload: PlanCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write(db, request, session_token, csrf_token)
    try:
        plan = db.execute(text("INSERT INTO plans (code, name) VALUES (:code, :name) RETURNING id, code, name, active, created_at"), {"code": payload.code, "name": payload.name.strip()}).mappings().one()
        for feature_code, limit_value in payload.limits.items():
            db.execute(text("INSERT INTO feature_limits (plan_id, feature_code, limit_value) VALUES (:plan_id, :feature_code, :limit_value)"), {"plan_id": plan["id"], "feature_code": feature_code, "limit_value": limit_value})
    except IntegrityError as exc:
        db.rollback()
        raise _error("DUPLICATE", "A plan with this code already exists.", status.HTTP_409_CONFLICT) from exc
    record_event(db, clinic_id=None, actor_user_id=session["user_id"], action="admin.plan.create", entity_type="plan", entity_id=plan["id"], outcome="success", request_id=UUID(request.state.request_id), metadata={"feature_count": len(payload.limits)})
    db.commit()
    return {"data": dict(plan), "meta": {"request_id": request.state.request_id}}


@router.put("/plans/{plan_id}/limits/{feature_code}")
def plan_limit_update(plan_id: UUID, feature_code: str, payload: PlanLimitUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write(db, request, session_token, csrf_token)
    row = db.execute(text("""
        INSERT INTO feature_limits (plan_id, feature_code, limit_value, enabled)
        SELECT id, :feature_code, :limit_value, :enabled FROM plans WHERE id = :plan_id
        ON CONFLICT (plan_id, feature_code) DO UPDATE SET limit_value = EXCLUDED.limit_value, enabled = EXCLUDED.enabled
        RETURNING plan_id, feature_code, limit_value, enabled
    """), {"plan_id": plan_id, "feature_code": feature_code, "limit_value": payload.limit_value, "enabled": payload.enabled}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Plan not found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=None, actor_user_id=session["user_id"], action="admin.plan_limit.update", entity_type="plan", entity_id=plan_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"feature_code": feature_code})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.get("/retention-policies")
def retention_policy_list(request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    _platform(db, session_token)
    cursor_values = decode_cursor(cursor, "admin-retention-policies") if cursor else None
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    try:
        after_created_at = datetime.fromisoformat(cursor_values["created_at"]) if cursor_values else None
        after_id = UUID(cursor_values["id"]) if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT id, name, jurisdiction, rules, approved_by, approved_at, active, created_at
        FROM retention_policies
        WHERE (:after_created_at IS NULL OR created_at < :after_created_at OR (created_at = :after_created_at AND id < :after_id))
        ORDER BY created_at DESC, id DESC
        LIMIT :page_size
    """), {"after_created_at": after_created_at, "after_id": after_id, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor("admin-retention-policies", {"created_at": rows[-1]["created_at"].isoformat(), "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@router.post("/retention-policies", status_code=status.HTTP_201_CREATED)
def retention_policy_create(payload: RetentionPolicyCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write(db, request, session_token, csrf_token)
    row = db.execute(text("""
        INSERT INTO retention_policies (name, jurisdiction, rules, active)
        VALUES (:name, :jurisdiction, CAST(:rules AS jsonb), false)
        RETURNING id, name, jurisdiction, rules, approved_by, approved_at, active, created_at
    """), {"name": payload.name.strip(), "jurisdiction": payload.jurisdiction.strip(), "rules": json.dumps(payload.rules, separators=(",", ":"), sort_keys=True)}).mappings().one()
    record_event(db, clinic_id=None, actor_user_id=session["user_id"], action="admin.retention_policy.create", entity_type="retention_policy", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id), metadata={"jurisdiction": row["jurisdiction"], "active": False})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.post("/retention-policies/{policy_id}/approve")
def retention_policy_approve(policy_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write(db, request, session_token, csrf_token)
    row = db.execute(text("""
        UPDATE retention_policies
        SET active = true, approved_by = :approved_by, approved_at = now()
        WHERE id = :id AND active = false
        RETURNING id, name, jurisdiction, rules, approved_by, approved_at, active, created_at
    """), {"id": policy_id, "approved_by": str(session["user_id"])}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Retention policy not found or already active.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=None, actor_user_id=session["user_id"], action="admin.retention_policy.approve", entity_type="retention_policy", entity_id=policy_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"jurisdiction": row["jurisdiction"]})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.put("/clinics/{clinic_id}/retention-policy")
def clinic_retention_policy_assign(clinic_id: UUID, payload: RetentionPolicyAssign, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write(db, request, session_token, csrf_token)
    row = db.execute(text("""
        UPDATE clinics AS c
        SET retention_policy_id = p.id, updated_at = now(), version = c.version + 1
        FROM retention_policies AS p
        WHERE c.id = :clinic_id AND p.id = :policy_id AND p.active = true
        RETURNING c.id AS clinic_id, p.id AS retention_policy_id, p.jurisdiction, p.approved_at, c.version
    """), {"clinic_id": clinic_id, "policy_id": payload.policy_id}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Clinic or active retention policy not found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=None, actor_user_id=session["user_id"], action="admin.retention_policy.assign", entity_type="clinic", entity_id=clinic_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"retention_policy_id": str(row["retention_policy_id"]), "jurisdiction": row["jurisdiction"]})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.get("/announcements")
def announcements_list(request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    _platform(db, session_token)
    cursor_values = decode_cursor(cursor, "admin-announcements") if cursor else None
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    try:
        after_starts_at = datetime.fromisoformat(cursor_values["starts_at"]) if cursor_values else None
        after_id = UUID(cursor_values["id"]) if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT id, title, body, severity, starts_at, ends_at, created_at
        FROM system_announcements
        WHERE (:after_starts_at IS NULL OR starts_at < :after_starts_at OR (starts_at = :after_starts_at AND id < :after_id))
        ORDER BY starts_at DESC, id DESC
        LIMIT :page_size
    """), {"after_starts_at": after_starts_at, "after_id": after_id, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor("admin-announcements", {"starts_at": rows[-1]["starts_at"].isoformat(), "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@router.post("/announcements", status_code=status.HTTP_201_CREATED)
def announcement_create(payload: AnnouncementCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write(db, request, session_token, csrf_token)
    ends_at = None
    if payload.ends_at:
        try:
            ends_at = datetime.fromisoformat(payload.ends_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise _error("INVALID_INPUT", "ends_at must be an RFC 3339 timestamp.", status.HTTP_400_BAD_REQUEST) from exc
    row = db.execute(text("INSERT INTO system_announcements (title, body, severity, ends_at) VALUES (:title, :body, :severity, :ends_at) RETURNING id, title, body, severity, starts_at, ends_at, created_at"), {"title": payload.title.strip(), "body": payload.body.strip(), "severity": payload.severity, "ends_at": ends_at}).mappings().one()
    record_event(db, clinic_id=None, actor_user_id=session["user_id"], action="admin.announcement.create", entity_type="system_announcement", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id), metadata={"severity": payload.severity})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.get("/clinics")
def clinics_list(request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    _platform(db, session_token)
    cursor_values = decode_cursor(cursor, "admin-clinics") if cursor else None
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    try:
        after_created_at = datetime.fromisoformat(cursor_values["created_at"]) if cursor_values else None
        after_id = UUID(cursor_values["id"]) if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT id, name, slug, status, timezone, locale, created_at, updated_at
        FROM clinics
        WHERE (:after_created_at IS NULL OR created_at < :after_created_at OR (created_at = :after_created_at AND id < :after_id))
        ORDER BY created_at DESC, id DESC
        LIMIT :page_size
    """), {"after_created_at": after_created_at, "after_id": after_id, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor("admin-clinics", {"created_at": rows[-1]["created_at"].isoformat(), "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@router.get("/metrics")
def metrics(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    _platform(db, session_token)
    pool = engine.pool
    pool_size = getattr(pool, "size", lambda: 0)()
    checked_out = getattr(pool, "checkedout", lambda: 0)()
    job_metrics = {"queued": 0, "running": 0, "failed": 0, "oldest_queued_at": None}
    telemetry = {
        "appointments": {"total": 0, "requested": 0, "confirmed": 0, "completed": 0, "cancelled": 0},
        "booking": {"attempts": 0, "conflicts": 0, "approval_delay_seconds": None, "no_show": 0, "no_show_rate": None},
        "scan_backlog": 0,
        "storage_failures": 0,
        "publish_failures": 0,
    }
    clinic_ids = db.execute(text("SELECT id FROM clinics WHERE archived_at IS NULL")).scalars().all()
    for clinic_id in clinic_ids:
        set_tenant_context(db, clinic_id)
        counts = db.execute(text("""
            SELECT COUNT(*) FILTER (WHERE status = 'queued') AS queued,
                   COUNT(*) FILTER (WHERE status = 'running') AS running,
                   COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                   MIN(created_at) FILTER (WHERE status = 'queued') AS oldest_queued_at
            FROM background_jobs WHERE clinic_id = :clinic_id
        """), {"clinic_id": clinic_id}).mappings().one()
        job_metrics["queued"] += counts["queued"]
        job_metrics["running"] += counts["running"]
        job_metrics["failed"] += counts["failed"]
        if counts["oldest_queued_at"] is not None and (job_metrics["oldest_queued_at"] is None or counts["oldest_queued_at"] < job_metrics["oldest_queued_at"]):
            job_metrics["oldest_queued_at"] = counts["oldest_queued_at"]
        appointment_counts = db.execute(text("""
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE status = 'requested') AS requested,
                   COUNT(*) FILTER (WHERE status = 'confirmed') AS confirmed,
                   COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                   COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled
            FROM appointments WHERE clinic_id = :clinic_id AND archived_at IS NULL
        """), {"clinic_id": clinic_id}).mappings().one()
        for key in telemetry["appointments"]:
            telemetry["appointments"][key] += appointment_counts[key]
        booking_events = db.execute(text("""
            SELECT COUNT(*) FILTER (WHERE action IN ('public_appointment.create', 'public_appointment.conflict')) AS attempts,
                   COUNT(*) FILTER (WHERE action = 'public_appointment.conflict') AS conflicts
            FROM audit_events
            WHERE clinic_id = :clinic_id
        """), {"clinic_id": clinic_id}).mappings().one()
        booking_quality = db.execute(text("""
            SELECT AVG(EXTRACT(EPOCH FROM (status_changed_at - created_at))) FILTER (WHERE status IN ('confirmed', 'completed') AND status_changed_at IS NOT NULL) AS approval_delay_seconds,
                   COUNT(*) FILTER (WHERE status = 'no_show') AS no_show,
                   COUNT(*) FILTER (WHERE status IN ('completed', 'no_show')) AS terminal_count
            FROM appointments WHERE clinic_id = :clinic_id AND archived_at IS NULL
        """), {"clinic_id": clinic_id}).mappings().one()
        telemetry["booking"]["attempts"] += booking_events["attempts"] or 0
        telemetry["booking"]["conflicts"] += booking_events["conflicts"] or 0
        telemetry["booking"]["no_show"] += booking_quality["no_show"] or 0
        if booking_quality["approval_delay_seconds"] is not None:
            current_delay = telemetry["booking"]["approval_delay_seconds"]
            telemetry["booking"]["approval_delay_seconds"] = float(booking_quality["approval_delay_seconds"]) if current_delay is None else (float(current_delay) + float(booking_quality["approval_delay_seconds"])) / 2
        if booking_quality["terminal_count"]:
            rate = (booking_quality["no_show"] or 0) / booking_quality["terminal_count"]
            current_rate = telemetry["booking"]["no_show_rate"]
            telemetry["booking"]["no_show_rate"] = float(rate) if current_rate is None else (float(current_rate) + float(rate)) / 2
        telemetry["scan_backlog"] += db.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM patient_documents WHERE clinic_id = :clinic_id AND archived_at IS NULL AND scan_status = 'pending_scan')
                + (SELECT COUNT(*) FROM website_media WHERE clinic_id = :clinic_id AND is_public = false AND scan_status = 'pending_scan')
        """), {"clinic_id": clinic_id}).scalar_one()
        failure_counts = db.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE status = 'failed' AND job_type IN ('document_scan', 'website_media_scan')) AS storage_failures,
                COUNT(*) FILTER (WHERE status = 'failed' AND job_type = 'website_publish') AS publish_failures
            FROM background_jobs WHERE clinic_id = :clinic_id
        """), {"clinic_id": clinic_id}).mappings().one()
        telemetry["storage_failures"] += failure_counts["storage_failures"]
        telemetry["publish_failures"] += failure_counts["publish_failures"]
    db.commit()
    return {"data": {"http": request_metrics.snapshot(), "database_pool": {"size": pool_size, "checked_out": checked_out, "overflow": getattr(pool, "overflow", lambda: 0)()}, "background_jobs": job_metrics, "telemetry": telemetry}, "meta": {"request_id": request.state.request_id}}

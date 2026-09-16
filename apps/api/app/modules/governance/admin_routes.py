from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.tenant import set_platform_context, set_tenant_context
from app.modules.audit.service import record_event
from app.modules.governance.schemas import AnnouncementCreate, PlanCreate, PlanLimitUpdate
from app.modules.identity.routes import _error, _session_or_401, _validate_origin
from app.modules.identity.service import SessionError, verify_csrf
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
    db.commit()
    return {"data": {"http": request_metrics.snapshot(), "database_pool": {"size": pool_size, "checked_out": checked_out, "overflow": getattr(pool, "overflow", lambda: 0)()}, "background_jobs": job_metrics}, "meta": {"request_id": request.state.request_id}}

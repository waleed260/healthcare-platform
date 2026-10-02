from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.tenant import set_tenant_context
from app.modules.audit.service import record_event
from app.modules.blueprint_core.routes import _authorized, _write_authorized
from app.modules.governance.admin_routes import _platform, _write
from app.modules.identity.routes import _error
from app.modules.upgrades.schemas import UpgradeDecision, UpgradeRequestCreate

router = APIRouter(prefix="/api/v1/upgrade-requests", tags=["upgrades"])
admin_router = APIRouter(prefix="/api/v1/admin", tags=["platform-admin"])

_COLUMNS = "id, clinic_id, kind, target_code, message, status, decision_note, decided_at, created_at"


@router.get("")
def upgrade_list(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "clinic.read")
    rows = db.execute(text(f"SELECT {_COLUMNS} FROM upgrade_requests WHERE clinic_id = :clinic_id ORDER BY created_at DESC LIMIT 100"), {"clinic_id": session["clinic_id"]}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.post("", status_code=status.HTTP_201_CREATED)
def upgrade_create(payload: UpgradeRequestCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "clinic.update", csrf_token)
    if payload.kind == "specialty":
        known = db.execute(text("SELECT 1 FROM specialties WHERE code = :code AND status = 'active'"), {"code": payload.target_code}).scalar_one_or_none()
        if known is None:
            raise _error("INVALID_INPUT", "That specialty does not exist.", status.HTTP_400_BAD_REQUEST)
        enabled = db.execute(text("""
            SELECT 1 FROM clinic_specialties cs JOIN specialties s ON s.id = cs.specialty_id
            WHERE cs.clinic_id = :clinic_id AND s.code = :code AND cs.status = 'active'
        """), {"clinic_id": session["clinic_id"], "code": payload.target_code}).scalar_one_or_none()
        if enabled is not None:
            raise _error("DUPLICATE", "This specialty is already enabled for your clinic.", status.HTTP_409_CONFLICT)
    try:
        row = db.execute(text(f"""
            INSERT INTO upgrade_requests (clinic_id, requested_by_user_id, kind, target_code, message)
            VALUES (:clinic_id, :user_id, :kind, :target_code, :message) RETURNING {_COLUMNS}
        """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], **payload.model_dump()}).mappings().one()
    except IntegrityError as exc:
        db.rollback()
        raise _error("DUPLICATE", "A request for this item is already waiting for review.", status.HTTP_409_CONFLICT) from exc
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="upgrade_request.create", entity_type="upgrade_request", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id), metadata={"kind": payload.kind, "target": payload.target_code})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.post("/{request_id}/cancel")
def upgrade_cancel(request_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "clinic.update", csrf_token)
    row = db.execute(text(f"UPDATE upgrade_requests SET status = 'cancelled', decided_at = now() WHERE clinic_id = :clinic_id AND id = :id AND status = 'pending' RETURNING {_COLUMNS}"), {"clinic_id": session["clinic_id"], "id": request_id}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "No pending request was found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="upgrade_request.cancel", entity_type="upgrade_request", entity_id=request_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@admin_router.get("/upgrade-requests")
def admin_upgrade_list(request: Request, status_filter: str = Query(default="pending", alias="status", pattern="^(pending|approved|declined|cancelled|all)$"), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    _platform(db, session_token)
    rows = db.execute(text("""
        SELECT r.id, r.clinic_id, c.name AS clinic_name, r.kind, r.target_code, r.message, r.status, r.decision_note, r.decided_at, r.created_at
        FROM upgrade_requests r JOIN clinics c ON c.id = r.clinic_id
        WHERE (:status = 'all' OR r.status = :status)
        ORDER BY r.created_at DESC LIMIT 200
    """), {"status": status_filter}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@admin_router.post("/upgrade-requests/{request_id}/decide")
def admin_upgrade_decide(request_id: UUID, payload: UpgradeDecision, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write(db, request, session_token, csrf_token)
    new_status = "approved" if payload.decision == "approve" else "declined"
    row = db.execute(text(f"""
        UPDATE upgrade_requests SET status = :status, decided_by_user_id = :user_id, decision_note = :note, decided_at = now()
        WHERE id = :id AND status = 'pending' RETURNING {_COLUMNS}
    """), {"status": new_status, "user_id": session["user_id"], "note": payload.note, "id": request_id}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "No pending request was found.", status.HTTP_404_NOT_FOUND)
    if new_status == "approved" and row["kind"] == "specialty":
        set_tenant_context(db, row["clinic_id"], session["user_id"])
        enabled = db.execute(text("""
            INSERT INTO clinic_specialties (clinic_id, specialty_id)
            SELECT :clinic_id, s.id FROM specialties s WHERE s.code = :code AND s.status = 'active'
            ON CONFLICT (clinic_id, specialty_id) DO UPDATE SET status = 'active', archived_at = NULL, version = clinic_specialties.version + 1
            RETURNING specialty_id
        """), {"clinic_id": row["clinic_id"], "code": row["target_code"]}).scalar_one_or_none()
        if enabled is None:
            db.rollback()
            raise _error("INVALID_INPUT", "The requested specialty is no longer available.", status.HTTP_400_BAD_REQUEST)
    record_event(db, clinic_id=None, actor_user_id=session["user_id"], action=f"admin.upgrade_request.{payload.decision}", entity_type="upgrade_request", entity_id=request_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"clinic_id": str(row["clinic_id"]), "kind": row["kind"], "target": row["target_code"]})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@admin_router.get("/overview")
def admin_overview(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    """Platform dashboard: clinic lifecycle, recurring revenue, renewals and client health (blueprint §4.1, §23)."""
    _platform(db, session_token)
    clinics = {row["status"]: row["count"] for row in db.execute(text("SELECT status, COUNT(*) AS count FROM clinics WHERE archived_at IS NULL GROUP BY status")).mappings().all()}
    recent_clinics = db.execute(text("SELECT COUNT(*) FROM clinics WHERE archived_at IS NULL AND created_at >= now() - interval '30 days'")).scalar_one()
    subscriptions = db.execute(text("""
        WITH latest AS (
            SELECT DISTINCT ON (cs.clinic_id) cs.clinic_id, cs.status, cs.renewal_at, cs.ends_at, p.code AS plan_code, p.monthly_price_minor, p.currency
            FROM clinic_subscriptions cs JOIN plans p ON p.id = cs.plan_id
            ORDER BY cs.clinic_id, cs.created_at DESC
        )
        SELECT
            COUNT(*) FILTER (WHERE status = 'active') AS active,
            COUNT(*) FILTER (WHERE status = 'trialing') AS trialing,
            COUNT(*) FILTER (WHERE status = 'past_due') AS past_due,
            COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled,
            COALESCE(SUM(monthly_price_minor) FILTER (WHERE status = 'active'), 0) AS mrr_minor,
            COALESCE(SUM(monthly_price_minor) FILTER (WHERE status = 'past_due'), 0) AS overdue_minor,
            COUNT(*) FILTER (WHERE status IN ('active', 'trialing') AND COALESCE(renewal_at, ends_at) BETWEEN now() AND now() + interval '30 days') AS renewals_30d,
            COUNT(*) FILTER (WHERE status = 'trialing' AND ends_at BETWEEN now() AND now() + interval '14 days') AS trials_ending_14d
        FROM latest
    """)).mappings().one()
    by_plan = db.execute(text("""
        SELECT p.code, COUNT(*) AS clinics FROM (
            SELECT DISTINCT ON (clinic_id) clinic_id, plan_id, status FROM clinic_subscriptions ORDER BY clinic_id, created_at DESC
        ) cs JOIN plans p ON p.id = cs.plan_id WHERE cs.status <> 'cancelled' GROUP BY p.code ORDER BY clinics DESC
    """)).mappings().all()
    modules = db.execute(text("""
        SELECT s.code, COUNT(*) AS clinics FROM clinic_specialties cs JOIN specialties s ON s.id = cs.specialty_id
        WHERE cs.status = 'active' GROUP BY s.code ORDER BY clinics DESC
    """)).mappings().all()
    open_requests = db.execute(text("SELECT COUNT(*) FROM upgrade_requests WHERE status = 'pending'")).scalar_one()
    health = []
    clinic_rows = db.execute(text("SELECT id, name FROM clinics WHERE archived_at IS NULL AND status = 'active' ORDER BY created_at DESC LIMIT 200")).mappings().all()
    for clinic in clinic_rows:
        set_tenant_context(db, clinic["id"])
        stats = db.execute(text("""
            SELECT (SELECT MAX(last_login_at) FROM users WHERE clinic_id = :id) AS last_login_at,
                   (SELECT COUNT(*) FROM users WHERE clinic_id = :id AND status = 'active') AS active_users,
                   (SELECT COUNT(*) FROM appointments WHERE clinic_id = :id AND created_at >= now() - interval '30 days') AS appointments_30d
        """), {"id": clinic["id"]}).mappings().one()
        risks = []
        if stats["last_login_at"] is None or stats["last_login_at"] < datetime.now(timezone.utc) - timedelta(days=14):
            risks.append("inactive_logins")
        if stats["appointments_30d"] == 0:
            risks.append("no_appointments")
        health.append({"clinic_id": clinic["id"], "name": clinic["name"], "last_login_at": stats["last_login_at"], "active_users": stats["active_users"], "appointments_30d": stats["appointments_30d"], "risks": risks})
    db.commit()
    at_risk = [item for item in health if item["risks"]]
    return {"data": {"clinics": {"by_status": clinics, "total": sum(clinics.values()), "onboarded_30d": recent_clinics}, "subscriptions": dict(subscriptions), "plans": [dict(row) for row in by_plan], "modules": [dict(row) for row in modules], "open_upgrade_requests": open_requests, "client_health": {"checked": len(health), "at_risk": at_risk[:25]}}, "meta": {"request_id": request.state.request_id}}

from __future__ import annotations

from datetime import datetime, time
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.tenant import set_tenant_context
from app.modules.audit.service import record_event
from app.modules.authorization.service import ForbiddenError, require_permission
from app.modules.identity.routes import _error, _session_or_401, _validate_origin
from app.modules.identity.service import SessionError, verify_csrf
from app.modules.scheduling.schemas import AvailabilityRuleCreate, BlockedSlotCreate, LeaveBlockCreate, ResourceBlockCreate
from app.core.security import decode_cursor, encode_cursor

router = APIRouter(prefix="/api/v1/scheduling", tags=["scheduling"])


def _authorized(db: Session, session_token: str | None, permission: str, branch_id: UUID | None = None) -> dict:
    session = _session_or_401(db, session_token)
    if session["clinic_id"] is None:
        raise _error("FORBIDDEN", "A clinic context is required.", status.HTTP_403_FORBIDDEN)
    set_tenant_context(db, session["clinic_id"], session["user_id"])
    try:
        require_permission(db, session["user_id"], session["clinic_id"], permission, branch_id=branch_id)
    except ForbiddenError as exc:
        raise _error("FORBIDDEN", "You do not have permission for scheduling.", status.HTTP_403_FORBIDDEN) from exc
    return session


def _session_with_tenant(db: Session, session_token: str | None) -> dict:
    session = _session_or_401(db, session_token)
    if session["clinic_id"] is None:
        raise _error("FORBIDDEN", "A clinic context is required.", status.HTTP_403_FORBIDDEN)
    set_tenant_context(db, session["clinic_id"], session["user_id"])
    return session


def _write(db: Session, request: Request, session_token: str | None, csrf_token: str | None, branch_id: UUID | None = None) -> dict:
    _validate_origin(request)
    session = _authorized(db, session_token, "schedule.manage", branch_id)
    if not csrf_token:
        raise _error("CSRF_REQUIRED", "A CSRF token is required.", status.HTTP_403_FORBIDDEN)
    try:
        verify_csrf(session, csrf_token)
    except SessionError as exc:
        raise _error("CSRF_INVALID", "The CSRF token is invalid.", status.HTTP_403_FORBIDDEN) from exc
    return session


def _event(db: Session, request: Request, session: dict, action: str, entity_type: str, entity_id: UUID) -> None:
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action=action, entity_type=entity_type, entity_id=entity_id, outcome="success", request_id=UUID(request.state.request_id))


def _ensure_branch_assignment(
    db: Session,
    clinic_id: UUID,
    branch_id: UUID,
    *,
    doctor_id: UUID | None = None,
    service_id: UUID | None = None,
) -> None:
    branch_exists = db.execute(
        text("SELECT 1 FROM branches WHERE clinic_id = :clinic_id AND id = :branch_id AND status = 'active' AND archived_at IS NULL"),
        {"clinic_id": clinic_id, "branch_id": branch_id},
    ).scalar_one_or_none()
    if branch_exists is None:
        raise _error("NOT_FOUND", "The branch is not in this clinic.", status.HTTP_404_NOT_FOUND)
    if doctor_id is not None:
        doctor_assigned = db.execute(
            text("""
                SELECT 1
                FROM branch_doctors bd
                JOIN doctor_profiles d ON d.clinic_id = bd.clinic_id AND d.id = bd.doctor_id
                WHERE bd.clinic_id = :clinic_id AND bd.branch_id = :branch_id AND bd.doctor_id = :doctor_id
                  AND d.status = 'active' AND d.archived_at IS NULL
            """),
            {"clinic_id": clinic_id, "branch_id": branch_id, "doctor_id": doctor_id},
        ).scalar_one_or_none()
        if doctor_assigned is None:
            raise _error("NOT_FOUND", "The doctor is not assigned to this branch.", status.HTTP_404_NOT_FOUND)
    if service_id is not None:
        service_assigned = db.execute(
            text("""
                SELECT 1
                FROM branch_services bs
                JOIN services s ON s.clinic_id = bs.clinic_id AND s.id = bs.service_id
                WHERE bs.clinic_id = :clinic_id AND bs.branch_id = :branch_id AND bs.service_id = :service_id
                  AND s.status = 'active' AND s.archived_at IS NULL
            """),
            {"clinic_id": clinic_id, "branch_id": branch_id, "service_id": service_id},
        ).scalar_one_or_none()
        if service_assigned is None:
            raise _error("NOT_FOUND", "The service is not assigned to this branch.", status.HTTP_404_NOT_FOUND)


@router.get("/availability-rules")
def availability_rule_list(request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "schedule.read")
    cursor_values = decode_cursor(cursor, "availability-rules") if cursor else None
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    zero_uuid = UUID("00000000-0000-0000-0000-000000000000")
    try:
        after_branch_id = UUID(cursor_values["branch_id"]) if cursor_values else None
        after_doctor_id = UUID(cursor_values["doctor_id"]) if cursor_values else None
        after_weekday = int(cursor_values["weekday"]) if cursor_values else None
        after_starts_at = time.fromisoformat(cursor_values["starts_at"]) if cursor_values else None
        after_service_id = UUID(cursor_values["service_id"]) if cursor_values and cursor_values.get("service_id") else None
        after_id = UUID(cursor_values["id"]) if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT id, branch_id, doctor_id, service_id, weekday, starts_at, ends_at, effective_from, effective_to, slot_cadence_minutes, version, created_at, updated_at
        FROM availability_rules
        WHERE clinic_id = :clinic_id
          AND (NOT EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id)
               OR EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id AND s.branch_id = availability_rules.branch_id))
          AND (
            :after_id IS NULL
            OR branch_id > :after_branch_id
            OR (branch_id = :after_branch_id AND doctor_id > :after_doctor_id)
            OR (branch_id = :after_branch_id AND doctor_id = :after_doctor_id AND weekday > :after_weekday)
            OR (branch_id = :after_branch_id AND doctor_id = :after_doctor_id AND weekday = :after_weekday AND starts_at > :after_starts_at)
            OR (branch_id = :after_branch_id AND doctor_id = :after_doctor_id AND weekday = :after_weekday AND starts_at = :after_starts_at AND COALESCE(service_id, :zero_uuid) > COALESCE(:after_service_id, :zero_uuid))
            OR (branch_id = :after_branch_id AND doctor_id = :after_doctor_id AND weekday = :after_weekday AND starts_at = :after_starts_at AND COALESCE(service_id, :zero_uuid) = COALESCE(:after_service_id, :zero_uuid) AND id > :after_id)
          )
        ORDER BY branch_id, doctor_id, weekday, starts_at, COALESCE(service_id, :zero_uuid), id
        LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "after_branch_id": after_branch_id, "after_doctor_id": after_doctor_id, "after_weekday": after_weekday, "after_starts_at": after_starts_at, "after_service_id": after_service_id, "after_id": after_id, "zero_uuid": zero_uuid, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_next and rows:
        last = rows[-1]
        next_cursor = encode_cursor("availability-rules", {"branch_id": str(last["branch_id"]), "doctor_id": str(last["doctor_id"]), "weekday": str(last["weekday"]), "starts_at": last["starts_at"].isoformat(), "service_id": str(last["service_id"]) if last["service_id"] else "", "id": str(last["id"])})
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@router.post("/availability-rules", status_code=status.HTTP_201_CREATED)
def availability_rule_create(payload: AvailabilityRuleCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write(db, request, session_token, csrf_token, payload.branch_id)
    _ensure_branch_assignment(db, session["clinic_id"], payload.branch_id, doctor_id=payload.doctor_id, service_id=payload.service_id)
    try:
        row = db.execute(text("""
            INSERT INTO availability_rules (clinic_id, branch_id, doctor_id, service_id, weekday, starts_at, ends_at, effective_from, effective_to, slot_cadence_minutes)
            VALUES (:clinic_id, :branch_id, :doctor_id, :service_id, :weekday, :starts_at, :ends_at, :effective_from, :effective_to, :cadence)
            RETURNING id, branch_id, doctor_id, service_id, weekday, starts_at, ends_at, effective_from, effective_to, slot_cadence_minutes, created_at
        """), {"clinic_id": session["clinic_id"], "branch_id": payload.branch_id, "doctor_id": payload.doctor_id, "service_id": payload.service_id, "weekday": payload.weekday, "starts_at": payload.starts_at, "ends_at": payload.ends_at, "effective_from": payload.effective_from, "effective_to": payload.effective_to, "cadence": payload.slot_cadence_minutes}).mappings().one()
    except IntegrityError as exc:
        db.rollback()
        raise _error("NOT_FOUND", "The branch, doctor, or service is not in this clinic.", status.HTTP_404_NOT_FOUND) from exc
    _event(db, request, session, "schedule.availability_rule_create", "availability_rule", row["id"])
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.delete("/availability-rules/{rule_id}")
def availability_rule_delete(rule_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _session_with_tenant(db, session_token)
    branch_id = db.execute(text("SELECT branch_id FROM availability_rules WHERE clinic_id = :clinic_id AND id = :id"), {"clinic_id": session["clinic_id"], "id": rule_id}).scalar_one_or_none()
    if branch_id is None:
        raise _error("NOT_FOUND", "Availability rule not found.", status.HTTP_404_NOT_FOUND)
    session = _write(db, request, session_token, csrf_token, branch_id=branch_id)
    deleted = db.execute(text("DELETE FROM availability_rules WHERE clinic_id = :clinic_id AND id = :id RETURNING id"), {"clinic_id": session["clinic_id"], "id": rule_id}).scalar_one_or_none()
    if deleted is None:
        raise _error("NOT_FOUND", "Availability rule not found.", status.HTTP_404_NOT_FOUND)
    _event(db, request, session, "schedule.availability_rule_delete", "availability_rule", rule_id)
    db.commit()
    return {"data": {"id": deleted, "deleted": True}, "meta": {"request_id": request.state.request_id}}


@router.get("/leave-blocks")
def leave_list(request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "schedule.read")
    cursor_values = decode_cursor(cursor, "leave-blocks") if cursor else None
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    try:
        after_starts_at = datetime.fromisoformat(cursor_values["starts_at"]) if cursor_values else None
        after_id = UUID(cursor_values["id"]) if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT id, doctor_id, branch_id, starts_at, ends_at, reason, created_at
        FROM leave_blocks
        WHERE clinic_id = :clinic_id
          AND (branch_id IS NULL
               OR NOT EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id)
               OR EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id AND s.branch_id = leave_blocks.branch_id))
          AND (:after_starts_at IS NULL OR starts_at > :after_starts_at OR (starts_at = :after_starts_at AND id > :after_id))
        ORDER BY starts_at, id
        LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "after_starts_at": after_starts_at, "after_id": after_id, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor("leave-blocks", {"starts_at": rows[-1]["starts_at"].isoformat(), "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@router.post("/leave-blocks", status_code=status.HTTP_201_CREATED)
def leave_create(payload: LeaveBlockCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write(db, request, session_token, csrf_token, payload.branch_id)
    if payload.branch_id is not None:
        _ensure_branch_assignment(db, session["clinic_id"], payload.branch_id, doctor_id=payload.doctor_id)
    try:
        row = db.execute(text("INSERT INTO leave_blocks (clinic_id, doctor_id, branch_id, starts_at, ends_at, reason) VALUES (:clinic_id, :doctor_id, :branch_id, :starts_at, :ends_at, :reason) RETURNING id, doctor_id, branch_id, starts_at, ends_at, reason, created_at"), {"clinic_id": session["clinic_id"], **payload.model_dump()}).mappings().one()
    except IntegrityError as exc:
        db.rollback()
        raise _error("NOT_FOUND", "The doctor or branch is not in this clinic.", status.HTTP_404_NOT_FOUND) from exc
    _event(db, request, session, "schedule.leave_create", "leave_block", row["id"])
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.delete("/leave-blocks/{block_id}")
def leave_delete(block_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _session_with_tenant(db, session_token)
    leave = db.execute(text("SELECT branch_id FROM leave_blocks WHERE clinic_id = :clinic_id AND id = :id"), {"clinic_id": session["clinic_id"], "id": block_id}).mappings().one_or_none()
    if leave is None:
        raise _error("NOT_FOUND", "Leave block not found.", status.HTTP_404_NOT_FOUND)
    session = _write(db, request, session_token, csrf_token, branch_id=leave["branch_id"])
    deleted = db.execute(text("DELETE FROM leave_blocks WHERE clinic_id = :clinic_id AND id = :id RETURNING id"), {"clinic_id": session["clinic_id"], "id": block_id}).scalar_one_or_none()
    if deleted is None:
        raise _error("NOT_FOUND", "Leave block not found.", status.HTTP_404_NOT_FOUND)
    _event(db, request, session, "schedule.leave_delete", "leave_block", block_id)
    db.commit()
    return {"data": {"id": deleted, "deleted": True}, "meta": {"request_id": request.state.request_id}}


@router.post("/blocked-slots", status_code=status.HTTP_201_CREATED)
def blocked_create(payload: BlockedSlotCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write(db, request, session_token, csrf_token, payload.branch_id)
    _ensure_branch_assignment(db, session["clinic_id"], payload.branch_id, doctor_id=payload.doctor_id)
    try:
        row = db.execute(text("INSERT INTO blocked_slots (clinic_id, branch_id, doctor_id, starts_at, ends_at, reason) VALUES (:clinic_id, :branch_id, :doctor_id, :starts_at, :ends_at, :reason) RETURNING id, branch_id, doctor_id, starts_at, ends_at, reason, created_at"), {"clinic_id": session["clinic_id"], **payload.model_dump()}).mappings().one()
    except IntegrityError as exc:
        db.rollback()
        raise _error("NOT_FOUND", "The branch or doctor is not in this clinic.", status.HTTP_404_NOT_FOUND) from exc
    _event(db, request, session, "schedule.blocked_slot_create", "blocked_slot", row["id"])
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.delete("/blocked-slots/{block_id}")
def blocked_delete(block_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _session_with_tenant(db, session_token)
    branch_id = db.execute(text("SELECT branch_id FROM blocked_slots WHERE clinic_id = :clinic_id AND id = :id"), {"clinic_id": session["clinic_id"], "id": block_id}).scalar_one_or_none()
    if branch_id is None:
        raise _error("NOT_FOUND", "Blocked slot not found.", status.HTTP_404_NOT_FOUND)
    session = _write(db, request, session_token, csrf_token, branch_id=branch_id)
    deleted = db.execute(text("DELETE FROM blocked_slots WHERE clinic_id = :clinic_id AND id = :id RETURNING id"), {"clinic_id": session["clinic_id"], "id": block_id}).scalar_one_or_none()
    if deleted is None:
        raise _error("NOT_FOUND", "Blocked slot not found.", status.HTTP_404_NOT_FOUND)
    _event(db, request, session, "schedule.blocked_slot_delete", "blocked_slot", block_id)
    db.commit()
    return {"data": {"id": deleted, "deleted": True}, "meta": {"request_id": request.state.request_id}}


@router.post("/resource-blocks", status_code=status.HTTP_201_CREATED)
def resource_block_create(payload: ResourceBlockCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write(db, request, session_token, csrf_token)
    try:
        row = db.execute(text("INSERT INTO resource_blocks (clinic_id, resource_id, starts_at, ends_at, reason) VALUES (:clinic_id, :resource_id, :starts_at, :ends_at, :reason) RETURNING id, resource_id, starts_at, ends_at, reason, created_at"), {"clinic_id": session["clinic_id"], **payload.model_dump()}).mappings().one()
    except IntegrityError as exc:
        db.rollback()
        raise _error("NOT_FOUND", "The resource is not in this clinic.", status.HTTP_404_NOT_FOUND) from exc
    _event(db, request, session, "schedule.resource_block_create", "resource_block", row["id"])
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.get("/resource-blocks")
def resource_block_list(request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "schedule.read")
    cursor_values = decode_cursor(cursor, "resource-blocks") if cursor else None
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    try:
        after_starts_at = datetime.fromisoformat(cursor_values["starts_at"]) if cursor_values else None
        after_id = UUID(cursor_values["id"]) if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT rb.id, rb.resource_id, rb.starts_at, rb.ends_at, rb.reason, rb.created_at
        FROM resource_blocks rb
        JOIN resources r ON r.clinic_id = rb.clinic_id AND r.id = rb.resource_id
        WHERE rb.clinic_id = :clinic_id
          AND (NOT EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id)
               OR EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id AND s.branch_id = r.branch_id))
          AND (:after_starts_at IS NULL OR rb.starts_at > :after_starts_at OR (rb.starts_at = :after_starts_at AND rb.id > :after_id))
        ORDER BY rb.starts_at, rb.id
        LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "after_starts_at": after_starts_at, "after_id": after_id, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor("resource-blocks", {"starts_at": rows[-1]["starts_at"].isoformat(), "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@router.delete("/resource-blocks/{block_id}")
def resource_block_delete(block_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _session_with_tenant(db, session_token)
    branch_id = db.execute(text("""
        SELECT r.branch_id
        FROM resource_blocks rb
        JOIN resources r ON r.clinic_id = rb.clinic_id AND r.id = rb.resource_id
        WHERE rb.clinic_id = :clinic_id AND rb.id = :id
    """), {"clinic_id": session["clinic_id"], "id": block_id}).scalar_one_or_none()
    if branch_id is None:
        raise _error("NOT_FOUND", "Resource block not found.", status.HTTP_404_NOT_FOUND)
    session = _write(db, request, session_token, csrf_token, branch_id=branch_id)
    deleted = db.execute(text("DELETE FROM resource_blocks WHERE clinic_id = :clinic_id AND id = :id RETURNING id"), {"clinic_id": session["clinic_id"], "id": block_id}).scalar_one_or_none()
    if deleted is None:
        raise _error("NOT_FOUND", "Resource block not found.", status.HTTP_404_NOT_FOUND)
    _event(db, request, session, "schedule.resource_block_delete", "resource_block", block_id)
    db.commit()
    return {"data": {"id": deleted, "deleted": True}, "meta": {"request_id": request.state.request_id}}

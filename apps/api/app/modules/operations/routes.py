from datetime import datetime

from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.tenant import set_tenant_context
from app.modules.appointments.state import validate_transition
from app.modules.authorization.service import ForbiddenError, require_permission
from app.modules.identity.routes import _error, _session_or_401, _validate_origin
from app.modules.identity.service import SessionError, verify_csrf
from app.modules.operations.schemas import FollowUpAssign, FollowUpComplete, FollowUpCreate, FollowUpUpdate, NotificationRead, PushSubscriptionCreate, QueueCheckIn, QueueCommand, QueueReorder
from app.core.security import decode_cursor, encode_cursor, encrypt_field
from app.modules.audit.service import record_event
import json
from uuid import UUID

router = APIRouter(prefix="/api/v1/operations", tags=["operations"])


def _authorized(db: Session, session_token: str | None, permission: str, branch_id=None) -> dict:
    session = _session_or_401(db, session_token)
    if session["clinic_id"] is None:
        raise _error("FORBIDDEN", "A clinic context is required.", status.HTTP_403_FORBIDDEN)
    set_tenant_context(db, session["clinic_id"], session["user_id"])
    try:
        require_permission(db, session["user_id"], session["clinic_id"], permission, branch_id=branch_id)
    except ForbiddenError as exc:
        raise _error("FORBIDDEN", "You do not have permission for this operation.", status.HTTP_403_FORBIDDEN) from exc
    return session


def _write_authorized(db: Session, request: Request, session_token: str | None, permission: str, csrf_token: str | None, branch_id=None) -> dict:
    _validate_origin(request)
    session = _authorized(db, session_token, permission, branch_id=branch_id)
    if not csrf_token:
        raise _error("CSRF_REQUIRED", "A CSRF token is required.", status.HTTP_403_FORBIDDEN)
    try:
        verify_csrf(session, csrf_token)
    except SessionError as exc:
        raise _error("CSRF_INVALID", "The CSRF token is invalid.", status.HTTP_403_FORBIDDEN) from exc
    return session


def _appointment_branch_id(db: Session, session: dict, appointment_id) -> object:
    branch_id = db.execute(text("""
        SELECT a.branch_id
        FROM appointments a
        JOIN branches b ON b.clinic_id = a.clinic_id AND b.id = a.branch_id
        WHERE a.clinic_id = :clinic_id AND a.id = :appointment_id AND a.archived_at IS NULL
          AND b.status = 'active' AND b.archived_at IS NULL
    """), {"clinic_id": session["clinic_id"], "appointment_id": appointment_id}).scalar_one_or_none()
    if branch_id is None:
        raise _error("NOT_FOUND", "Appointment not found.", status.HTTP_404_NOT_FOUND)
    return branch_id


def _follow_up_patient_and_appointment(db: Session, session: dict, patient_id, appointment_id) -> object:
    patient_exists = db.execute(text("SELECT 1 FROM patients WHERE clinic_id = :clinic_id AND id = :patient_id AND archived_at IS NULL"), {"clinic_id": session["clinic_id"], "patient_id": patient_id}).scalar_one_or_none()
    if patient_exists is None:
        raise _error("NOT_FOUND", "Patient not found.", status.HTTP_404_NOT_FOUND)
    if appointment_id is None:
        return None
    appointment = db.execute(text("""
        SELECT a.branch_id, a.patient_id
        FROM appointments a
        JOIN branches b ON b.clinic_id = a.clinic_id AND b.id = a.branch_id
        WHERE a.clinic_id = :clinic_id AND a.id = :appointment_id AND a.archived_at IS NULL
          AND b.status = 'active' AND b.archived_at IS NULL
    """), {"clinic_id": session["clinic_id"], "appointment_id": appointment_id}).mappings().one_or_none()
    if appointment is None or appointment["patient_id"] != patient_id:
        raise _error("NOT_FOUND", "The appointment is not associated with this patient.", status.HTTP_404_NOT_FOUND)
    return appointment["branch_id"]


def _queue_context(db: Session, session_token: str | None, queue_id: str) -> tuple[dict, dict]:
    session = _session_or_401(db, session_token)
    if session["clinic_id"] is None:
        raise _error("FORBIDDEN", "A clinic context is required.", status.HTTP_403_FORBIDDEN)
    set_tenant_context(db, session["clinic_id"], session["user_id"])
    row = db.execute(text("""
        SELECT q.id, q.appointment_id, q.status, q.version, a.branch_id
        FROM queue_entries q
        JOIN appointments a ON a.clinic_id = q.clinic_id AND a.id = q.appointment_id
        JOIN branches b ON b.clinic_id = a.clinic_id AND b.id = a.branch_id
        WHERE q.clinic_id = :clinic_id AND q.id = :queue_id
          AND a.archived_at IS NULL AND b.status = 'active' AND b.archived_at IS NULL
        FOR UPDATE
    """), {"clinic_id": session["clinic_id"], "queue_id": queue_id}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Queue entry not found.", status.HTTP_404_NOT_FOUND)
    return session, dict(row)


def _follow_up_context(db: Session, session_token: str | None, follow_up_id: str) -> tuple[dict, dict]:
    session = _session_or_401(db, session_token)
    if session["clinic_id"] is None:
        raise _error("FORBIDDEN", "A clinic context is required.", status.HTTP_403_FORBIDDEN)
    set_tenant_context(db, session["clinic_id"], session["user_id"])
    row = db.execute(text("""
        SELECT f.id, f.patient_id, f.appointment_id, f.status, f.version, a.branch_id
        FROM follow_up_tasks f
        JOIN patients p ON p.clinic_id = f.clinic_id AND p.id = f.patient_id
        LEFT JOIN appointments a ON a.clinic_id = f.clinic_id AND a.id = f.appointment_id
        LEFT JOIN branches b ON b.clinic_id = a.clinic_id AND b.id = a.branch_id
        WHERE f.clinic_id = :clinic_id AND f.id = :follow_up_id AND p.archived_at IS NULL
          AND (a.id IS NULL OR (a.archived_at IS NULL AND b.status = 'active' AND b.archived_at IS NULL))
        FOR UPDATE
    """), {"clinic_id": session["clinic_id"], "follow_up_id": follow_up_id}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Follow-up task not found.", status.HTTP_404_NOT_FOUND)
    return session, dict(row)


@router.get("/dashboard-summary")
def dashboard_summary(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "appointment.read")
    clinic_id = session["clinic_id"]
    counts = db.execute(text("""
        SELECT
          COUNT(*) FILTER (WHERE starts_at::date = (now() AT TIME ZONE b.timezone)::date) AS today_appointments,
          COUNT(*) FILTER (WHERE status = 'requested') AS pending_approvals,
          COUNT(*) FILTER (WHERE status = 'no_show') AS no_shows
        FROM appointments a JOIN branches b ON b.id = a.branch_id AND b.clinic_id = a.clinic_id
        WHERE a.clinic_id = :clinic_id AND a.archived_at IS NULL
          AND b.status = 'active' AND b.archived_at IS NULL
          AND (NOT EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id)
               OR EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id AND s.branch_id = a.branch_id))
    """), {"clinic_id": clinic_id, "user_id": session["user_id"]}).mappings().one()
    queue_count = db.execute(text("""
        SELECT COUNT(*)
        FROM queue_entries q
        JOIN appointments a ON a.clinic_id = q.clinic_id AND a.id = q.appointment_id
        JOIN branches b ON b.clinic_id = a.clinic_id AND b.id = a.branch_id
        WHERE q.clinic_id = :clinic_id AND q.status IN ('waiting', 'in_consultation')
          AND a.archived_at IS NULL AND b.status = 'active' AND b.archived_at IS NULL
          AND (NOT EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id)
               OR EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id AND s.branch_id = a.branch_id))
    """), {"clinic_id": clinic_id, "user_id": session["user_id"]}).scalar_one()
    followups_due = db.execute(text("""
        SELECT COUNT(*) FROM follow_up_tasks f
        JOIN patients p ON p.clinic_id = f.clinic_id AND p.id = f.patient_id
        LEFT JOIN appointments a ON a.clinic_id = f.clinic_id AND a.id = f.appointment_id
        WHERE f.clinic_id = :clinic_id AND f.status IN ('due', 'contacted', 'booked') AND f.due_at <= now() AND p.archived_at IS NULL
          AND (a.branch_id IS NULL
               OR NOT EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id)
               OR EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id AND s.branch_id = a.branch_id))
    """), {"clinic_id": clinic_id, "user_id": session["user_id"]}).scalar_one()
    db.commit()
    return {"data": {**dict(counts), "waiting_patients": queue_count, "followups_due": followups_due}, "meta": {"request_id": request.state.request_id}}


@router.get("/queue")
def queue_list(request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "queue.read")
    cursor_values = decode_cursor(cursor, "queue") if cursor else None
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    try:
        after_priority = int(cursor_values["priority"]) if cursor_values else None
        after_checked_in_at = datetime.fromisoformat(cursor_values["checked_in_at"]) if cursor_values else None
        after_id = UUID(cursor_values["id"]) if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT q.id, q.appointment_id, q.status, q.checked_in_at, q.priority, q.version,
               p.full_name, a.reference, a.starts_at
        FROM queue_entries q
        JOIN appointments a ON a.id = q.appointment_id AND a.clinic_id = q.clinic_id
        JOIN patients p ON p.id = a.patient_id AND p.clinic_id = a.clinic_id
        JOIN branches b ON b.id = a.branch_id AND b.clinic_id = a.clinic_id
        WHERE q.clinic_id = :clinic_id AND q.status IN ('waiting', 'in_consultation')
          AND a.archived_at IS NULL AND p.archived_at IS NULL
          AND b.status = 'active' AND b.archived_at IS NULL
          AND (NOT EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id)
               OR EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id AND s.branch_id = a.branch_id))
          AND (:after_priority IS NULL OR q.priority < :after_priority
               OR (q.priority = :after_priority AND q.checked_in_at > :after_checked_in_at)
               OR (q.priority = :after_priority AND q.checked_in_at = :after_checked_in_at AND q.id > :after_id))
        ORDER BY q.priority DESC, q.checked_in_at, q.id
        LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "after_priority": after_priority, "after_checked_in_at": after_checked_in_at, "after_id": after_id, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_next and rows:
        next_cursor = encode_cursor("queue", {"priority": str(rows[-1]["priority"]), "checked_in_at": rows[-1]["checked_in_at"].isoformat(), "id": str(rows[-1]["id"])})
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@router.post("/queue/check-in", status_code=status.HTTP_201_CREATED)
def queue_check_in(payload: QueueCheckIn, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _session_or_401(db, session_token)
    if session["clinic_id"] is None:
        raise _error("FORBIDDEN", "A clinic context is required.", status.HTTP_403_FORBIDDEN)
    set_tenant_context(db, session["clinic_id"], session["user_id"])
    branch_id = _appointment_branch_id(db, session, payload.appointment_id)
    session = _write_authorized(db, request, session_token, "queue.manage", csrf_token, branch_id=branch_id)
    try:
        require_permission(db, session["user_id"], session["clinic_id"], "queue.manage", branch_id=branch_id)
    except ForbiddenError as exc:
        raise _error("FORBIDDEN", "You do not have permission for this operation.", status.HTTP_403_FORBIDDEN) from exc
    row = db.execute(text("SELECT id, status, version, clinic_id FROM appointments WHERE id = :appointment_id AND clinic_id = :clinic_id FOR UPDATE"), {"appointment_id": payload.appointment_id, "clinic_id": session["clinic_id"]}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Appointment not found.", status.HTTP_404_NOT_FOUND)
    if row["version"] != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The appointment changed before check-in.", status.HTTP_409_CONFLICT)
    try:
        validate_transition(row["status"], "arrived")
    except ValueError as exc:
        raise _error("INVALID_TRANSITION", "This appointment cannot be checked in.", status.HTTP_400_BAD_REQUEST) from exc
    db.execute(text("UPDATE appointments SET status = 'waiting', status_changed_at = now(), version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :id"), {"clinic_id": session["clinic_id"], "id": payload.appointment_id})
    db.execute(text("INSERT INTO appointment_history (clinic_id, appointment_id, from_status, to_status, actor_user_id) VALUES (:clinic_id, :appointment_id, :from_status, 'arrived', :actor), (:clinic_id, :appointment_id, 'arrived', 'waiting', :actor)"), {"clinic_id": session["clinic_id"], "appointment_id": payload.appointment_id, "from_status": row["status"], "actor": session["user_id"]})
    queue = db.execute(text("INSERT INTO queue_entries (clinic_id, appointment_id) VALUES (:clinic_id, :appointment_id) RETURNING id, status, checked_in_at"), {"clinic_id": session["clinic_id"], "appointment_id": payload.appointment_id}).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="queue.check_in", entity_type="queue_entry", entity_id=queue["id"], outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(queue), "meta": {"request_id": request.state.request_id}}


@router.post("/queue/{queue_id}/start")
def queue_start(queue_id: str, payload: QueueCommand, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    _, queue = _queue_context(db, session_token, queue_id)
    session = _write_authorized(db, request, session_token, "queue.manage", csrf_token, branch_id=queue["branch_id"])
    if queue["version"] != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The queue entry changed before starting consultation.", status.HTTP_409_CONFLICT)
    if queue["status"] != "waiting":
        raise _error("INVALID_STATE", "Only waiting queue entries can start consultation.", status.HTTP_400_BAD_REQUEST)
    appointment = db.execute(text("SELECT status FROM appointments WHERE clinic_id = :clinic_id AND id = :appointment_id AND archived_at IS NULL FOR UPDATE"), {"clinic_id": session["clinic_id"], "appointment_id": queue["appointment_id"]}).mappings().one_or_none()
    if appointment is None:
        raise _error("NOT_FOUND", "Appointment not found.", status.HTTP_404_NOT_FOUND)
    if appointment["status"] != "waiting":
        raise _error("INVALID_STATE", "The appointment is not waiting for consultation.", status.HTTP_400_BAD_REQUEST)
    result = db.execute(text("""
        UPDATE queue_entries
        SET status = 'in_consultation', started_at = now(), version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :id
        RETURNING id, status, started_at, version
    """), {"clinic_id": session["clinic_id"], "id": queue_id}).mappings().one()
    db.execute(text("UPDATE appointments SET status = 'in_consultation', blocks_time = true, status_changed_at = now(), version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :appointment_id"), {"clinic_id": session["clinic_id"], "appointment_id": queue["appointment_id"]})
    db.execute(text("INSERT INTO appointment_history (clinic_id, appointment_id, from_status, to_status, actor_user_id) VALUES (:clinic_id, :appointment_id, 'waiting', 'in_consultation', :actor)"), {"clinic_id": session["clinic_id"], "appointment_id": queue["appointment_id"], "actor": session["user_id"]})
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="queue.start", entity_type="queue_entry", entity_id=queue["id"], outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(result), "meta": {"request_id": request.state.request_id}}


@router.post("/queue/{queue_id}/complete")
def queue_complete(queue_id: str, payload: QueueCommand, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    _, queue = _queue_context(db, session_token, queue_id)
    session = _write_authorized(db, request, session_token, "queue.manage", csrf_token, branch_id=queue["branch_id"])
    if queue["version"] != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The queue entry changed before completion.", status.HTTP_409_CONFLICT)
    if queue["status"] != "in_consultation":
        raise _error("INVALID_STATE", "Only active consultations can be completed.", status.HTTP_400_BAD_REQUEST)
    appointment = db.execute(text("SELECT status FROM appointments WHERE clinic_id = :clinic_id AND id = :appointment_id AND archived_at IS NULL FOR UPDATE"), {"clinic_id": session["clinic_id"], "appointment_id": queue["appointment_id"]}).mappings().one_or_none()
    if appointment is None:
        raise _error("NOT_FOUND", "Appointment not found.", status.HTTP_404_NOT_FOUND)
    if appointment["status"] != "in_consultation":
        raise _error("INVALID_STATE", "The appointment is not in consultation.", status.HTTP_400_BAD_REQUEST)
    result = db.execute(text("""
        UPDATE queue_entries
        SET status = 'completed', completed_at = now(), version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :id
        RETURNING id, appointment_id, status, completed_at, version
    """), {"clinic_id": session["clinic_id"], "id": queue_id}).mappings().one()
    db.execute(text("""
        UPDATE appointments
        SET status = 'completed', blocks_time = false, status_changed_at = now(), version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :appointment_id AND status = 'in_consultation'
    """), {"clinic_id": session["clinic_id"], "appointment_id": queue["appointment_id"]})
    db.execute(text("""
        INSERT INTO appointment_history (clinic_id, appointment_id, from_status, to_status, actor_user_id)
        SELECT :clinic_id, :appointment_id, 'in_consultation', 'completed', :actor
        WHERE EXISTS (SELECT 1 FROM appointments WHERE clinic_id = :clinic_id AND id = :appointment_id AND status = 'completed')
    """), {"clinic_id": session["clinic_id"], "appointment_id": queue["appointment_id"], "actor": session["user_id"]})
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="queue.complete", entity_type="queue_entry", entity_id=queue["id"], outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(result), "meta": {"request_id": request.state.request_id}}


@router.post("/queue/{queue_id}/reorder")
def queue_reorder(queue_id: str, payload: QueueReorder, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    _, queue = _queue_context(db, session_token, queue_id)
    session = _write_authorized(db, request, session_token, "queue.manage", csrf_token, branch_id=queue["branch_id"])
    if queue["version"] != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The queue entry changed before reordering.", status.HTTP_409_CONFLICT)
    if queue["status"] not in {"waiting", "in_consultation"}:
        raise _error("INVALID_STATE", "Only active queue entries can be reordered.", status.HTTP_400_BAD_REQUEST)
    result = db.execute(text("""
        UPDATE queue_entries
        SET priority = :priority, priority_reason = :priority_reason, version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :id
        RETURNING id, priority, priority_reason, status, version
    """), {"clinic_id": session["clinic_id"], "id": queue_id, "priority": payload.priority, "priority_reason": payload.priority_reason}).mappings().one()
    db.commit()
    return {"data": dict(result), "meta": {"request_id": request.state.request_id}}


@router.get("/follow-ups")
def follow_up_list(request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "followup.read")
    cursor_values = decode_cursor(cursor, "follow-ups") if cursor else None
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    try:
        after_due_at = datetime.fromisoformat(cursor_values["due_at"]) if cursor_values else None
        after_priority = cursor_values["priority"] if cursor_values else None
        after_created_at = datetime.fromisoformat(cursor_values["created_at"]) if cursor_values else None
        after_id = UUID(cursor_values["id"]) if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT f.id, f.patient_id, f.appointment_id, f.assignee_user_id, f.reason, f.due_at, f.priority,
               CASE WHEN f.status IN ('due', 'contacted', 'booked') AND f.due_at < now() THEN 'overdue' ELSE f.status END AS status,
               f.outcome_note, f.completed_at, f.version, f.created_at, f.updated_at
        FROM follow_up_tasks f
        JOIN patients p ON p.clinic_id = f.clinic_id AND p.id = f.patient_id
        LEFT JOIN appointments a ON a.clinic_id = f.clinic_id AND a.id = f.appointment_id
        LEFT JOIN branches b ON b.clinic_id = a.clinic_id AND b.id = a.branch_id
        WHERE f.clinic_id = :clinic_id AND f.status NOT IN ('closed') AND p.archived_at IS NULL
          AND (a.id IS NULL OR (a.archived_at IS NULL AND b.status = 'active' AND b.archived_at IS NULL))
          AND (a.branch_id IS NULL
               OR NOT EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id)
               OR EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id AND s.branch_id = a.branch_id))
          AND (:after_due_at IS NULL OR f.due_at > :after_due_at
               OR (f.due_at = :after_due_at AND f.priority < :after_priority)
               OR (f.due_at = :after_due_at AND f.priority = :after_priority AND f.created_at > :after_created_at)
               OR (f.due_at = :after_due_at AND f.priority = :after_priority AND f.created_at = :after_created_at AND f.id > :after_id))
        ORDER BY f.due_at, f.priority DESC, f.created_at, f.id
        LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "after_due_at": after_due_at, "after_priority": after_priority, "after_created_at": after_created_at, "after_id": after_id, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_next and rows:
        next_cursor = encode_cursor("follow-ups", {"due_at": rows[-1]["due_at"].isoformat(), "priority": rows[-1]["priority"], "created_at": rows[-1]["created_at"].isoformat(), "id": str(rows[-1]["id"])})
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@router.get("/follow-ups/due-count")
def follow_up_due_count(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "followup.read")
    count = db.execute(text("""
        SELECT COUNT(*)
        FROM follow_up_tasks f
        JOIN patients p ON p.clinic_id = f.clinic_id AND p.id = f.patient_id
        LEFT JOIN appointments a ON a.clinic_id = f.clinic_id AND a.id = f.appointment_id
        LEFT JOIN branches b ON b.clinic_id = a.clinic_id AND b.id = a.branch_id
        WHERE f.clinic_id = :clinic_id AND f.status IN ('due', 'contacted', 'booked') AND f.due_at <= now() AND p.archived_at IS NULL
          AND (a.id IS NULL OR (a.archived_at IS NULL AND b.status = 'active' AND b.archived_at IS NULL))
          AND (a.branch_id IS NULL
               OR NOT EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id)
               OR EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id AND s.branch_id = a.branch_id))
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"]}).scalar_one()
    db.commit()
    return {"data": {"due_count": count}, "meta": {"request_id": request.state.request_id}}


@router.get("/activity")
def operations_activity(request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "audit.read")
    cursor_values = decode_cursor(cursor, "operations-activity") if cursor else None
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    try:
        after_created_at = datetime.fromisoformat(cursor_values["created_at"]) if cursor_values else None
        after_id = UUID(cursor_values["id"]) if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT id, action, entity_type, entity_id, outcome, created_at
        FROM audit_events
        WHERE clinic_id = :clinic_id AND (action LIKE 'queue.%' OR action LIKE 'followup.%' OR action LIKE 'notification.%')
          AND (:after_created_at IS NULL OR created_at < :after_created_at OR (created_at = :after_created_at AND id < :after_id))
        ORDER BY created_at DESC, id DESC
        LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "after_created_at": after_created_at, "after_id": after_id, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_next and rows:
        next_cursor = encode_cursor("operations-activity", {"created_at": rows[-1]["created_at"].isoformat(), "id": str(rows[-1]["id"])})
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@router.post("/follow-ups", status_code=status.HTTP_201_CREATED)
def follow_up_create(payload: FollowUpCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _session_or_401(db, session_token)
    if session["clinic_id"] is None:
        raise _error("FORBIDDEN", "A clinic context is required.", status.HTTP_403_FORBIDDEN)
    set_tenant_context(db, session["clinic_id"], session["user_id"])
    branch_id = _follow_up_patient_and_appointment(db, session, payload.patient_id, payload.appointment_id)
    session = _write_authorized(db, request, session_token, "followup.manage", csrf_token, branch_id=branch_id)
    try:
        row = db.execute(text("""
            INSERT INTO follow_up_tasks (clinic_id, patient_id, appointment_id, assignee_user_id, reason, due_at, priority)
            SELECT :clinic_id, :patient_id, :appointment_id, :assignee_user_id, :reason, :due_at, :priority
            WHERE :assignee_user_id IS NULL OR EXISTS (
                SELECT 1 FROM users
                WHERE clinic_id = :clinic_id AND id = :assignee_user_id
                  AND status = 'active' AND archived_at IS NULL
            )
            RETURNING id, patient_id, appointment_id, assignee_user_id, reason, due_at, priority, status, version, created_at
        """), {"clinic_id": session["clinic_id"], **payload.model_dump()}).mappings().one_or_none()
        if row is None:
            raise _error("NOT_FOUND", "The assignee was not found.", status.HTTP_404_NOT_FOUND)
    except IntegrityError as exc:
        db.rollback()
        raise _error("NOT_FOUND", "The patient, appointment, or assignee was not found.", status.HTTP_404_NOT_FOUND) from exc
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.post("/follow-ups/{follow_up_id}/update")
def follow_up_update(follow_up_id: str, payload: FollowUpUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    _, follow_up = _follow_up_context(db, session_token, follow_up_id)
    session = _write_authorized(db, request, session_token, "followup.manage", csrf_token, branch_id=follow_up["branch_id"])
    if follow_up["version"] != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The follow-up changed before update.", status.HTTP_409_CONFLICT)
    if follow_up["status"] in {"completed", "closed"}:
        raise _error("INVALID_STATE", "Completed follow-ups cannot be updated.", status.HTTP_400_BAD_REQUEST)
    result = db.execute(text("""
        UPDATE follow_up_tasks
        SET reason = COALESCE(:reason, reason),
            due_at = COALESCE(:due_at, due_at),
            priority = COALESCE(:priority, priority),
            version = version + 1,
            updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :id
        RETURNING id, reason, due_at, priority, status, version, updated_at
    """), {"clinic_id": session["clinic_id"], "id": follow_up_id, "reason": payload.reason, "due_at": payload.due_at, "priority": payload.priority}).mappings().one()
    db.commit()
    return {"data": dict(result), "meta": {"request_id": request.state.request_id}}


@router.post("/follow-ups/{follow_up_id}/assign")
def follow_up_assign(follow_up_id: str, payload: FollowUpAssign, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    _, follow_up = _follow_up_context(db, session_token, follow_up_id)
    session = _write_authorized(db, request, session_token, "followup.manage", csrf_token, branch_id=follow_up["branch_id"])
    if follow_up["version"] != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The follow-up changed before assignment.", status.HTTP_409_CONFLICT)
    if follow_up["status"] in {"completed", "closed"}:
        raise _error("INVALID_STATE", "Completed follow-ups cannot be assigned.", status.HTTP_400_BAD_REQUEST)
    try:
        result = db.execute(text("""
            UPDATE follow_up_tasks
            SET assignee_user_id = :assignee_user_id, version = version + 1, updated_at = now()
            WHERE clinic_id = :clinic_id AND id = :id
              AND (:assignee_user_id IS NULL OR EXISTS (
                  SELECT 1 FROM users
                  WHERE clinic_id = :clinic_id AND id = :assignee_user_id
                    AND status = 'active' AND archived_at IS NULL
              ))
            RETURNING id, assignee_user_id, status, version, updated_at
        """), {"clinic_id": session["clinic_id"], "id": follow_up_id, "assignee_user_id": payload.assignee_user_id}).mappings().one_or_none()
        if result is None:
            raise _error("NOT_FOUND", "The assignee was not found.", status.HTTP_404_NOT_FOUND)
    except IntegrityError as exc:
        db.rollback()
        raise _error("NOT_FOUND", "The assignee was not found.", status.HTTP_404_NOT_FOUND) from exc
    db.commit()
    return {"data": dict(result), "meta": {"request_id": request.state.request_id}}


@router.post("/follow-ups/{follow_up_id}/complete")
def follow_up_complete(follow_up_id: str, payload: FollowUpComplete, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    _, follow_up = _follow_up_context(db, session_token, follow_up_id)
    session = _write_authorized(db, request, session_token, "followup.manage", csrf_token, branch_id=follow_up["branch_id"])
    if follow_up["version"] != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The follow-up changed before completion.", status.HTTP_409_CONFLICT)
    if follow_up["status"] in ("completed", "closed"):
        raise _error("INVALID_STATE", "This follow-up is already closed.", status.HTTP_400_BAD_REQUEST)
    result = db.execute(text("""
        UPDATE follow_up_tasks
        SET status = 'completed', outcome_note = :outcome_note, completed_at = now(), version = version + 1, updated_at = now()
        WHERE id = :id AND clinic_id = :clinic_id
        RETURNING id, status, outcome_note, completed_at, version
    """), {"id": follow_up_id, "clinic_id": session["clinic_id"], "outcome_note": payload.outcome_note}).mappings().one()
    db.commit()
    return {"data": dict(result), "meta": {"request_id": request.state.request_id}}


@router.get("/notifications")
def notification_list(request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "notification.read")
    cursor_values = decode_cursor(cursor, "notifications") if cursor else None
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    try:
        after_created_at = datetime.fromisoformat(cursor_values["created_at"]) if cursor_values else None
        after_id = UUID(cursor_values["id"]) if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT id, kind, title, body, read_at, created_at
        FROM notifications
        WHERE clinic_id = :clinic_id AND user_id = :user_id
          AND (:after_created_at IS NULL OR created_at < :after_created_at OR (created_at = :after_created_at AND id < :after_id))
        ORDER BY created_at DESC, id DESC
        LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "after_created_at": after_created_at, "after_id": after_id, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_next and rows:
        next_cursor = encode_cursor("notifications", {"created_at": rows[-1]["created_at"].isoformat(), "id": str(rows[-1]["id"])})
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@router.post("/notifications/read")
def notification_mark_read(payload: NotificationRead, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "notification.manage", csrf_token)
    result = db.execute(text("""
        UPDATE notifications SET read_at = COALESCE(read_at, now())
        WHERE clinic_id = :clinic_id AND user_id = :user_id AND id = ANY(:notification_ids)
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "notification_ids": [str(item) for item in payload.notification_ids]})
    db.commit()
    return {"data": {"marked_read": result.rowcount}, "meta": {"request_id": request.state.request_id}}


@router.get("/notifications/push-subscriptions")
def push_subscription_list(request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "notification.read")
    cursor_values = decode_cursor(cursor, "push-subscriptions") if cursor else None
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    try:
        after_created_at = datetime.fromisoformat(cursor_values["created_at"]) if cursor_values else None
        after_id = UUID(cursor_values["id"]) if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT id, endpoint, created_at
        FROM browser_push_subscriptions
        WHERE clinic_id = :clinic_id AND user_id = :user_id AND revoked_at IS NULL
          AND (:after_created_at IS NULL OR created_at < :after_created_at OR (created_at = :after_created_at AND id < :after_id))
        ORDER BY created_at DESC, id DESC
        LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "after_created_at": after_created_at, "after_id": after_id, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_next and rows:
        next_cursor = encode_cursor("push-subscriptions", {"created_at": rows[-1]["created_at"].isoformat(), "id": str(rows[-1]["id"])})
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@router.post("/notifications/push-subscriptions", status_code=status.HTTP_201_CREATED)
def push_subscription_create(payload: PushSubscriptionCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "notification.manage", csrf_token)
    try:
        row = db.execute(text("""
            INSERT INTO browser_push_subscriptions (clinic_id, user_id, endpoint, encrypted_credentials)
            VALUES (:clinic_id, :user_id, :endpoint, :credentials)
            ON CONFLICT (endpoint) DO UPDATE
            SET clinic_id = EXCLUDED.clinic_id, user_id = EXCLUDED.user_id,
                encrypted_credentials = EXCLUDED.encrypted_credentials, revoked_at = NULL
            RETURNING id, endpoint, created_at
        """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "endpoint": str(payload.endpoint), "credentials": encrypt_field(json.dumps({"p256dh": payload.p256dh, "auth": payload.auth}))}).mappings().one()
    except Exception as exc:
        db.rollback()
        raise _error("PUSH_SUBSCRIPTION_FAILED", "The browser notification subscription could not be saved.", status.HTTP_409_CONFLICT) from exc
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="notification.push_subscribe", entity_type="browser_push_subscription", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.delete("/notifications/push-subscriptions/{subscription_id}")
def push_subscription_revoke(subscription_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "notification.manage", csrf_token)
    row = db.execute(text("""
        UPDATE browser_push_subscriptions
        SET revoked_at = COALESCE(revoked_at, now())
        WHERE clinic_id = :clinic_id AND user_id = :user_id AND id = :id
        RETURNING id, revoked_at
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "id": subscription_id}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Push subscription not found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="notification.push_revoke", entity_type="browser_push_subscription", entity_id=subscription_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import decode_cursor, encode_cursor
from app.db.session import get_db
from app.db.tenant import set_tenant_context
from app.modules.audit.service import record_event
from app.modules.authorization.service import ForbiddenError, require_permission
from app.modules.identity.routes import _error, _session_or_401, _validate_origin
from app.modules.identity.service import SessionError, verify_csrf
from app.modules.tasks.schemas import TaskCreate, TaskUpdate

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


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


@router.get("")
def task_list(
    status_filter: str | None = Query(default=None, alias="status", max_length=40),
    assignee: str | None = Query(default=None, alias="assignee_user_id", max_length=64),
    priority: str | None = Query(default=None, max_length=20),
    cursor: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=50, ge=1, le=100),
    request: Request = None,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
) -> dict:
    session = _authorized(db, session_token, "appointment.read")
    cursor_values = decode_cursor(cursor, "tasks") if cursor else None
    rows = db.execute(text("""
        SELECT t.id, t.title, t.description, t.task_type, t.priority, t.status,
               t.assignee_user_id, t.patient_id, t.lead_id, t.appointment_id,
               t.due_at, t.completed_at, t.created_by, t.created_at, t.version,
               u.display_name AS assignee_name,
               p.full_name AS patient_name
        FROM internal_tasks t
        LEFT JOIN access_tokens at2 ON at2.clinic_id = t.clinic_id AND at2.user_id = t.assignee_user_id AND at2.revoked_at IS NULL
        LEFT JOIN users u ON u.id = t.assignee_user_id
        LEFT JOIN patients p ON p.clinic_id = t.clinic_id AND p.id = t.patient_id AND p.archived_at IS NULL
        WHERE t.clinic_id = :clinic_id AND t.archived_at IS NULL
          AND (:status IS NULL OR t.status = :status)
          AND (:assignee IS NULL OR t.assignee_user_id = CAST(:assignee AS uuid))
          AND (:priority IS NULL OR t.priority = :priority)
          AND (:after_created_at IS NULL OR (t.created_at, t.id) < (CAST(:after_created_at AS timestamptz), CAST(:after_id AS uuid)))
        ORDER BY
          CASE t.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,
          COALESCE(t.due_at, '2099-12-31'::timestamptz),
          t.created_at DESC, t.id DESC
        LIMIT :page_size
    """), {
        "clinic_id": session["clinic_id"],
        "status": status_filter,
        "assignee": assignee,
        "priority": priority,
        "after_created_at": cursor_values.get("created_at") if cursor_values else None,
        "after_id": cursor_values.get("id") if cursor_values else None,
        "page_size": limit + 1,
    }).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor("tasks", {"created_at": rows[-1]["created_at"].isoformat(), "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@router.post("", status_code=status.HTTP_201_CREATED)
def task_create(
    payload: TaskCreate,
    request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    session = _write_authorized(db, request, session_token, "appointment.read", csrf_token)
    row = db.execute(text("""
        INSERT INTO internal_tasks (clinic_id, title, description, task_type, priority, assignee_user_id, patient_id, lead_id, appointment_id, due_at, created_by)
        VALUES (:clinic_id, :title, :description, :task_type, :priority, :assignee_user_id, :patient_id, :lead_id, :appointment_id, :due_at, :created_by)
        RETURNING id, title, description, task_type, priority, status, assignee_user_id, patient_id, lead_id, appointment_id, due_at, created_by, created_at, version
    """), {
        "clinic_id": session["clinic_id"],
        "title": payload.title.strip(),
        "description": payload.description,
        "task_type": payload.task_type,
        "priority": payload.priority,
        "assignee_user_id": payload.assignee_user_id,
        "patient_id": payload.patient_id,
        "lead_id": payload.lead_id,
        "appointment_id": payload.appointment_id,
        "due_at": payload.due_at,
        "created_by": session["user_id"],
    }).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="task.create", entity_type="internal_task", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.patch("/{task_id}")
def task_update(
    task_id: UUID,
    payload: TaskUpdate,
    request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    session = _write_authorized(db, request, session_token, "appointment.read", csrf_token)
    current = db.execute(text("SELECT version FROM internal_tasks WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL FOR UPDATE"), {"clinic_id": session["clinic_id"], "id": task_id}).scalar_one_or_none()
    if current is None:
        raise _error("NOT_FOUND", "Task not found.", status.HTTP_404_NOT_FOUND)
    if current != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The task changed before update.", status.HTTP_409_CONFLICT)
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    updates = []
    params: dict = {"clinic_id": session["clinic_id"], "id": task_id}
    for field, val in values.items():
        updates.append(f"{field} = :{field}")
        params[field] = val
    if values.get("status") == "completed":
        updates.append("completed_at = now()")
    if not updates:
        raise _error("INVALID_INPUT", "At least one field is required.", status.HTTP_400_BAD_REQUEST)
    row = db.execute(text(f"""
        UPDATE internal_tasks SET {', '.join(updates)}, version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :id
        RETURNING id, title, description, task_type, priority, status, assignee_user_id, patient_id, due_at, completed_at, version, updated_at
    """), params).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="task.update", entity_type="internal_task", entity_id=task_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"fields": sorted(values.keys())})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.delete("/{task_id}")
def task_archive(
    task_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    session = _write_authorized(db, request, session_token, "appointment.read", csrf_token)
    result = db.execute(text("UPDATE internal_tasks SET archived_at = now() WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL RETURNING id"), {"clinic_id": session["clinic_id"], "id": task_id}).scalar_one_or_none()
    if result is None:
        raise _error("NOT_FOUND", "Task not found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="task.archive", entity_type="internal_task", entity_id=task_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": {"id": str(result)}, "meta": {"request_id": request.state.request_id}}

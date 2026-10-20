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
from app.modules.inventory.schemas import InventoryStatusUpdate, WarehouseCreate, WarehouseUpdate

router = APIRouter(prefix="/api/v1/warehouses", tags=["warehouses"])


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
def warehouse_list(
    request: Request,
    status_filter: str = Query(default="active", alias="status"),
    cursor: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
) -> dict:
    session = _authorized(db, session_token, "warehouse.read")
    values = decode_cursor(cursor, "warehouses") if cursor else {}
    if cursor and values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    values = values or {}
    rows = db.execute(text("""
        SELECT w.id, w.name, w.code, w.address, w.warehouse_type, w.branch_id, b.name AS branch_name,
               w.contact_name, w.contact_phone, w.status, w.version, w.created_at, w.updated_at
        FROM warehouses w
        JOIN branches b ON b.clinic_id = w.clinic_id AND b.id = w.branch_id
        WHERE w.clinic_id = :clinic_id AND (:status IS NULL OR w.status = :status)
          AND (:after_name IS NULL OR w.name > :after_name OR (w.name = :after_name AND w.id > CAST(:after_id AS uuid)))
        ORDER BY w.name, w.id LIMIT :page_size
    """), {
        "clinic_id": session["clinic_id"], "status": status_filter if status_filter != "all" else None,
        "after_name": values.get("name"), "after_id": values.get("id"), "page_size": limit + 1,
    }).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor("warehouses", {"name": rows[-1]["name"], "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor}}


@router.post("", status_code=status.HTTP_201_CREATED)
def warehouse_create(
    payload: WarehouseCreate, request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    session = _write_authorized(db, request, session_token, "warehouse.manage", csrf_token)
    branch = db.execute(text("SELECT id FROM branches WHERE clinic_id = :clinic_id AND id = :branch_id AND status = 'active' AND archived_at IS NULL"),
                        {"clinic_id": session["clinic_id"], "branch_id": payload.branch_id}).scalar_one_or_none()
    if branch is None:
        raise _error("NOT_FOUND", "Branch not found or inactive.", status.HTTP_400_BAD_REQUEST)
    try:
        row = db.execute(text("""
            INSERT INTO warehouses (clinic_id, name, code, branch_id, warehouse_type, contact_name, contact_phone, address)
            VALUES (:clinic_id, :name, :code, :branch_id, :warehouse_type, :contact_name, :contact_phone, CAST(:address AS jsonb))
            RETURNING id, name, code, branch_id, warehouse_type, contact_name, contact_phone, address, status, version, created_at
        """), {"clinic_id": session["clinic_id"], "name": payload.name, "code": payload.code,
               "branch_id": payload.branch_id, "warehouse_type": payload.warehouse_type,
               "contact_name": payload.contact_name, "contact_phone": payload.contact_phone,
               "address": __import__("json").dumps(payload.address) if payload.address else None}).mappings().one()
    except Exception as exc:
        db.rollback()
        if "uq_warehouses_code" in str(exc):
            raise _error("DUPLICATE", "A warehouse with this code already exists.", status.HTTP_409_CONFLICT) from exc
        raise
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"],
                 action="inventory.warehouse.create", entity_type="warehouse", entity_id=row["id"],
                 outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.patch("/{warehouse_id}")
def warehouse_update(
    warehouse_id: UUID, payload: WarehouseUpdate, request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    session = _write_authorized(db, request, session_token, "warehouse.manage", csrf_token)
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    if not values:
        raise _error("INVALID_INPUT", "At least one field must be provided.", status.HTTP_400_BAD_REQUEST)
    if "address" in values and values["address"] is not None:
        values["address"] = __import__("json").dumps(values["address"])
    if "branch_id" in values:
        branch = db.execute(text("SELECT id FROM branches WHERE clinic_id = :clinic_id AND id = :branch_id AND status = 'active'"),
                            {"clinic_id": session["clinic_id"], "branch_id": values["branch_id"]}).scalar_one_or_none()
        if branch is None:
            raise _error("NOT_FOUND", "Branch not found or inactive.", status.HTTP_400_BAD_REQUEST)
    assignments = ", ".join(
        f"address = CAST(:{field} AS jsonb)" if field == "address" else f"{field} = :{field}"
        for field in values
    )
    try:
        row = db.execute(text(
            f"UPDATE warehouses SET {assignments}, version = version + 1, updated_at = now() "
            f"WHERE clinic_id = :clinic_id AND id = :id AND version = :expected_version "
            f"RETURNING id, name, code, branch_id, warehouse_type, contact_name, contact_phone, address, status, version, updated_at"
        ), {"clinic_id": session["clinic_id"], "id": warehouse_id, "expected_version": payload.expected_version, **values}).mappings().one_or_none()
    except Exception as exc:
        db.rollback()
        if "uq_warehouses_code" in str(exc):
            raise _error("DUPLICATE", "A warehouse with this code already exists.", status.HTTP_409_CONFLICT) from exc
        raise
    if row is None:
        raise _error("VERSION_CONFLICT", "The warehouse changed before this update.", status.HTTP_409_CONFLICT)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"],
                 action="inventory.warehouse.update", entity_type="warehouse", entity_id=warehouse_id,
                 outcome="success", request_id=UUID(request.state.request_id), metadata={"fields": sorted(values)})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.post("/{warehouse_id}/status")
def warehouse_status(
    warehouse_id: UUID, payload: InventoryStatusUpdate, request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    session = _write_authorized(db, request, session_token, "warehouse.manage", csrf_token)
    row = db.execute(text(
        "UPDATE warehouses SET status = :status, archived_at = CASE WHEN :status = 'archived' THEN COALESCE(archived_at, now()) ELSE NULL END, "
        "version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :id "
        "RETURNING id, name, status, version, updated_at"
    ), {"clinic_id": session["clinic_id"], "id": warehouse_id, "status": payload.status}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Warehouse not found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"],
                 action="inventory.warehouse.status", entity_type="warehouse", entity_id=warehouse_id,
                 outcome="success", request_id=UUID(request.state.request_id), metadata={"status": payload.status})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}

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
from app.modules.inventory.schemas import TransferCancel, TransferCreate, TransferHandover, TransferReceive

router = APIRouter(prefix="/api/v1/transfers", tags=["transfers"])


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


def _next_transfer_number(db: Session, clinic_id: UUID) -> str:
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(CAST(:key AS text), 0))"),
               {"key": f"tf-seq:{clinic_id}"})
    row = db.execute(text(
        "INSERT INTO transfer_number_sequences (clinic_id, next_value) VALUES (:clinic_id, 2) "
        "ON CONFLICT (clinic_id) DO UPDATE SET next_value = transfer_number_sequences.next_value + 1 "
        "RETURNING next_value - 1 AS seq"
    ), {"clinic_id": clinic_id}).mappings().one()
    return f"TF-{row['seq']:04d}"


@router.get("")
def transfer_list(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    cursor: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
) -> dict:
    session = _authorized(db, session_token, "transfer.read")
    values = decode_cursor(cursor, "transfers") if cursor else {}
    if cursor and values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    values = values or {}
    rows = db.execute(text("""
        SELECT t.id, t.transfer_number, t.status,
               t.source_warehouse_id, sw.name AS source_warehouse_name,
               t.destination_warehouse_id, dw.name AS destination_warehouse_name,
               t.initiated_by_user_id, u.display_name AS initiated_by_name,
               t.driver_name, t.handed_over_at, t.received_at, t.cancelled_at,
               t.version, t.created_at,
               (SELECT COUNT(*) FROM inventory_transfer_lines l WHERE l.clinic_id = t.clinic_id AND l.transfer_id = t.id) AS line_count
        FROM inventory_transfers t
        JOIN warehouses sw ON sw.clinic_id = t.clinic_id AND sw.id = t.source_warehouse_id
        JOIN warehouses dw ON dw.clinic_id = t.clinic_id AND dw.id = t.destination_warehouse_id
        JOIN users u ON u.clinic_id = t.clinic_id AND u.id = t.initiated_by_user_id
        WHERE t.clinic_id = :clinic_id
          AND (:status IS NULL OR t.status = :status)
          AND (:after_created IS NULL OR t.created_at < CAST(:after_created AS timestamptz)
               OR (t.created_at = CAST(:after_created AS timestamptz) AND t.id < CAST(:after_id AS uuid)))
        ORDER BY t.created_at DESC, t.id DESC LIMIT :page_size
    """), {
        "clinic_id": session["clinic_id"], "status": status_filter,
        "after_created": values.get("created_at"), "after_id": values.get("id"), "page_size": limit + 1,
    }).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor("transfers", {"created_at": str(rows[-1]["created_at"]), "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor}}


@router.post("", status_code=status.HTTP_201_CREATED)
def transfer_create(
    payload: TransferCreate, request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    session = _write_authorized(db, request, session_token, "transfer.manage", csrf_token)
    src = db.execute(text("SELECT id, branch_id, name FROM warehouses WHERE clinic_id = :clinic_id AND id = :id AND status = 'active'"),
                     {"clinic_id": session["clinic_id"], "id": payload.source_warehouse_id}).mappings().one_or_none()
    if src is None:
        raise _error("NOT_FOUND", "Source warehouse not found or inactive.", status.HTTP_400_BAD_REQUEST)
    dst = db.execute(text("SELECT id, branch_id, name FROM warehouses WHERE clinic_id = :clinic_id AND id = :id AND status = 'active'"),
                     {"clinic_id": session["clinic_id"], "id": payload.destination_warehouse_id}).mappings().one_or_none()
    if dst is None:
        raise _error("NOT_FOUND", "Destination warehouse not found or inactive.", status.HTTP_400_BAD_REQUEST)
    for line in payload.lines:
        product = db.execute(text("SELECT id FROM inventory_products WHERE clinic_id = :clinic_id AND id = :id AND status = 'active' AND archived_at IS NULL"),
                             {"clinic_id": session["clinic_id"], "id": line.product_id}).scalar_one_or_none()
        if product is None:
            raise _error("NOT_FOUND", f"Product {line.product_id} not found or inactive.", status.HTTP_400_BAD_REQUEST)
        stock = db.execute(text(
            "SELECT quantity FROM inventory_stock WHERE clinic_id = :clinic_id AND branch_id = :branch_id AND product_id = :product_id"
        ), {"clinic_id": session["clinic_id"], "branch_id": src["branch_id"], "product_id": line.product_id}).scalar_one_or_none()
        available = stock if stock is not None else 0
        if available < line.quantity_sent:
            raise _error("INSUFFICIENT_STOCK", f"Insufficient stock at source warehouse. Available: {available}, requested: {line.quantity_sent}.", status.HTTP_409_CONFLICT)
    transfer_number = _next_transfer_number(db, session["clinic_id"])
    tf = db.execute(text("""
        INSERT INTO inventory_transfers (clinic_id, transfer_number, source_warehouse_id, destination_warehouse_id, status, initiated_by_user_id, notes)
        VALUES (:clinic_id, :transfer_number, :source_id, :dest_id, 'created', :user_id, :notes)
        RETURNING id, transfer_number, source_warehouse_id, destination_warehouse_id, status, initiated_by_user_id, notes, version, created_at
    """), {"clinic_id": session["clinic_id"], "transfer_number": transfer_number,
           "source_id": payload.source_warehouse_id, "dest_id": payload.destination_warehouse_id,
           "user_id": session["user_id"], "notes": payload.notes}).mappings().one()
    lines_out = []
    for line in payload.lines:
        l_row = db.execute(text("""
            INSERT INTO inventory_transfer_lines (clinic_id, transfer_id, product_id, quantity_sent)
            VALUES (:clinic_id, :transfer_id, :product_id, :quantity_sent)
            RETURNING id, product_id, quantity_sent, quantity_received, condition
        """), {"clinic_id": session["clinic_id"], "transfer_id": tf["id"],
               "product_id": line.product_id, "quantity_sent": line.quantity_sent}).mappings().one()
        lines_out.append(dict(l_row))
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"],
                 action="inventory.transfer.create", entity_type="inventory_transfer", entity_id=tf["id"],
                 outcome="success", request_id=UUID(request.state.request_id),
                 metadata={"transfer_number": transfer_number, "line_count": len(payload.lines)})
    db.commit()
    return {"data": {**dict(tf), "lines": lines_out}, "meta": {"request_id": request.state.request_id}}


@router.get("/{transfer_id}")
def transfer_detail(
    transfer_id: UUID, request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
) -> dict:
    session = _authorized(db, session_token, "transfer.read")
    tf = db.execute(text("""
        SELECT t.id, t.transfer_number, t.status, t.notes, t.version, t.created_at, t.updated_at,
               t.source_warehouse_id, sw.name AS source_warehouse_name, sw.code AS source_warehouse_code, sb.name AS source_branch_name,
               t.destination_warehouse_id, dw.name AS dest_warehouse_name, dw.code AS dest_warehouse_code, db.name AS dest_branch_name,
               t.initiated_by_user_id, iu.display_name AS initiated_by_name,
               t.driver_name, t.driver_phone,
               t.handed_over_by_user_id, hu.display_name AS handed_over_by_name, t.handed_over_at,
               t.received_by_user_id, ru.display_name AS received_by_name, t.received_at,
               t.cancelled_by_user_id, cu.display_name AS cancelled_by_name, t.cancelled_at, t.cancel_reason
        FROM inventory_transfers t
        JOIN warehouses sw ON sw.clinic_id = t.clinic_id AND sw.id = t.source_warehouse_id
        JOIN branches sb ON sb.clinic_id = sw.clinic_id AND sb.id = sw.branch_id
        JOIN warehouses dw ON dw.clinic_id = t.clinic_id AND dw.id = t.destination_warehouse_id
        JOIN branches db ON db.clinic_id = dw.clinic_id AND db.id = dw.branch_id
        JOIN users iu ON iu.clinic_id = t.clinic_id AND iu.id = t.initiated_by_user_id
        LEFT JOIN users hu ON hu.clinic_id = t.clinic_id AND hu.id = t.handed_over_by_user_id
        LEFT JOIN users ru ON ru.clinic_id = t.clinic_id AND ru.id = t.received_by_user_id
        LEFT JOIN users cu ON cu.clinic_id = t.clinic_id AND cu.id = t.cancelled_by_user_id
        WHERE t.clinic_id = :clinic_id AND t.id = :id
    """), {"clinic_id": session["clinic_id"], "id": transfer_id}).mappings().one_or_none()
    if tf is None:
        raise _error("NOT_FOUND", "Transfer not found.", status.HTTP_404_NOT_FOUND)
    lines = db.execute(text("""
        SELECT l.id, l.product_id, p.name AS product_name, p.sku, p.unit,
               l.quantity_sent, l.quantity_received, l.condition,
               l.checked_by_user_id, cu.display_name AS checked_by_name, l.checked_at, l.notes
        FROM inventory_transfer_lines l
        JOIN inventory_products p ON p.clinic_id = l.clinic_id AND p.id = l.product_id
        LEFT JOIN users cu ON cu.clinic_id = l.clinic_id AND cu.id = l.checked_by_user_id
        WHERE l.clinic_id = :clinic_id AND l.transfer_id = :transfer_id
    """), {"clinic_id": session["clinic_id"], "transfer_id": transfer_id}).mappings().all()
    db.commit()
    return {"data": {**dict(tf), "lines": [dict(l) for l in lines]}, "meta": {"request_id": request.state.request_id}}


@router.post("/{transfer_id}/handover")
def transfer_handover(
    transfer_id: UUID, payload: TransferHandover, request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    session = _write_authorized(db, request, session_token, "transfer.manage", csrf_token)
    tf = db.execute(text(
        "SELECT id, status, version, transfer_number, destination_warehouse_id FROM inventory_transfers "
        "WHERE clinic_id = :clinic_id AND id = :id"
    ), {"clinic_id": session["clinic_id"], "id": transfer_id}).mappings().one_or_none()
    if tf is None:
        raise _error("NOT_FOUND", "Transfer not found.", status.HTTP_404_NOT_FOUND)
    if tf["status"] != "created":
        raise _error("INVALID_INPUT", "Transfer must be in 'created' status for handover.", status.HTTP_409_CONFLICT)
    if tf["version"] != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The transfer changed before this update.", status.HTTP_409_CONFLICT)
    db.execute(text(
        "UPDATE inventory_transfers SET status = 'handover_for_transit', driver_name = :driver_name, driver_phone = :driver_phone, "
        "handed_over_by_user_id = :user_id, handed_over_at = now(), version = version + 1, updated_at = now() "
        "WHERE clinic_id = :clinic_id AND id = :id"
    ), {"clinic_id": session["clinic_id"], "id": transfer_id, "driver_name": payload.driver_name,
        "driver_phone": payload.driver_phone, "user_id": session["user_id"]})
    db.execute(text("""
        INSERT INTO notifications (clinic_id, user_id, kind, title, body)
        SELECT :clinic_id, u.id, 'transfer.in_transit', 'Transfer en route', :body
        FROM users u
        JOIN user_roles ur ON ur.clinic_id = u.clinic_id AND ur.user_id = u.id
        JOIN role_permissions rp ON rp.role_id = ur.role_id AND rp.permission_code = 'transfer.manage'
        WHERE u.clinic_id = :clinic_id AND u.status = 'active' AND u.archived_at IS NULL AND u.id != :actor_id
        LIMIT 10
    """), {"clinic_id": session["clinic_id"], "body": f"Transfer {tf['transfer_number']} has been dispatched and is en route.",
           "actor_id": session["user_id"]})
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"],
                 action="inventory.transfer.handover", entity_type="inventory_transfer", entity_id=transfer_id,
                 outcome="success", request_id=UUID(request.state.request_id),
                 metadata={"driver_name": payload.driver_name})
    db.commit()
    return {"data": {"id": transfer_id, "status": "handover_for_transit", "driver_name": payload.driver_name}, "meta": {"request_id": request.state.request_id}}


@router.post("/{transfer_id}/receive")
def transfer_receive(
    transfer_id: UUID, payload: TransferReceive, request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    session = _write_authorized(db, request, session_token, "transfer.manage", csrf_token)
    tf = db.execute(text("""
        SELECT t.id, t.status, t.version, t.transfer_number, t.initiated_by_user_id,
               t.source_warehouse_id, t.destination_warehouse_id,
               sw.branch_id AS source_branch_id, dw.branch_id AS dest_branch_id
        FROM inventory_transfers t
        JOIN warehouses sw ON sw.clinic_id = t.clinic_id AND sw.id = t.source_warehouse_id
        JOIN warehouses dw ON dw.clinic_id = t.clinic_id AND dw.id = t.destination_warehouse_id
        WHERE t.clinic_id = :clinic_id AND t.id = :id
    """), {"clinic_id": session["clinic_id"], "id": transfer_id}).mappings().one_or_none()
    if tf is None:
        raise _error("NOT_FOUND", "Transfer not found.", status.HTTP_404_NOT_FOUND)
    if tf["status"] != "handover_for_transit":
        raise _error("INVALID_INPUT", "Transfer must be in 'handover_for_transit' status to receive.", status.HTTP_409_CONFLICT)
    if tf["version"] != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The transfer changed before this update.", status.HTTP_409_CONFLICT)
    source_branch_id = tf["source_branch_id"]
    dest_branch_id = tf["dest_branch_id"]
    source_warehouse_id = tf["source_warehouse_id"]
    dest_warehouse_id = tf["destination_warehouse_id"]
    for recv_line in payload.lines:
        tl = db.execute(text(
            "SELECT id, product_id, quantity_sent FROM inventory_transfer_lines "
            "WHERE clinic_id = :clinic_id AND id = :line_id AND transfer_id = :transfer_id"
        ), {"clinic_id": session["clinic_id"], "line_id": recv_line.line_id, "transfer_id": transfer_id}).mappings().one_or_none()
        if tl is None:
            raise _error("NOT_FOUND", f"Transfer line {recv_line.line_id} not found.", status.HTTP_400_BAD_REQUEST)
        db.execute(text(
            "UPDATE inventory_transfer_lines SET quantity_received = :qty, condition = :condition, "
            "checked_by_user_id = :user_id, checked_at = now(), notes = :notes "
            "WHERE clinic_id = :clinic_id AND id = :id"
        ), {"clinic_id": session["clinic_id"], "id": recv_line.line_id, "qty": recv_line.quantity_received,
            "condition": recv_line.condition, "user_id": session["user_id"], "notes": recv_line.notes})
        src_stock = db.execute(text(
            "SELECT id, quantity FROM inventory_stock WHERE clinic_id = :clinic_id AND branch_id = :branch_id AND product_id = :product_id"
            " AND (warehouse_id = :warehouse_id OR (warehouse_id IS NULL AND :warehouse_id IS NULL)) FOR UPDATE"
        ), {"clinic_id": session["clinic_id"], "branch_id": source_branch_id, "product_id": tl["product_id"], "warehouse_id": source_warehouse_id}).mappings().one_or_none()
        if src_stock is None:
            src_stock = db.execute(text(
                "SELECT id, quantity FROM inventory_stock WHERE clinic_id = :clinic_id AND branch_id = :branch_id AND product_id = :product_id AND warehouse_id IS NULL FOR UPDATE"
            ), {"clinic_id": session["clinic_id"], "branch_id": source_branch_id, "product_id": tl["product_id"]}).mappings().one_or_none()
        if src_stock is not None:
            new_qty = max(0, src_stock["quantity"] - tl["quantity_sent"])
            db.execute(text("UPDATE inventory_stock SET quantity = :qty, version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :id"),
                       {"clinic_id": session["clinic_id"], "id": src_stock["id"], "qty": new_qty})
        db.execute(text(
            "INSERT INTO inventory_adjustments (clinic_id, branch_id, product_id, delta, reason, adjusted_by_user_id, warehouse_id) "
            "VALUES (:clinic_id, :branch_id, :product_id, :delta, :reason, :user_id, :warehouse_id)"
        ), {"clinic_id": session["clinic_id"], "branch_id": source_branch_id, "product_id": tl["product_id"],
            "delta": -tl["quantity_sent"], "reason": f"Transfer out {tf['transfer_number']}",
            "user_id": session["user_id"], "warehouse_id": source_warehouse_id})
        dst_stock = db.execute(text(
            "SELECT id, quantity FROM inventory_stock WHERE clinic_id = :clinic_id AND branch_id = :branch_id AND product_id = :product_id"
            " AND (warehouse_id = :warehouse_id OR (warehouse_id IS NULL AND :warehouse_id IS NULL)) FOR UPDATE"
        ), {"clinic_id": session["clinic_id"], "branch_id": dest_branch_id, "product_id": tl["product_id"], "warehouse_id": dest_warehouse_id}).mappings().one_or_none()
        if dst_stock is None:
            db.execute(text(
                "INSERT INTO inventory_stock (clinic_id, branch_id, product_id, quantity, warehouse_id) VALUES (:clinic_id, :branch_id, :product_id, :qty, :warehouse_id)"
            ), {"clinic_id": session["clinic_id"], "branch_id": dest_branch_id, "product_id": tl["product_id"], "qty": recv_line.quantity_received, "warehouse_id": dest_warehouse_id})
        else:
            db.execute(text(
                "UPDATE inventory_stock SET quantity = quantity + :qty, version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :id"
            ), {"clinic_id": session["clinic_id"], "id": dst_stock["id"], "qty": recv_line.quantity_received})
        db.execute(text(
            "INSERT INTO inventory_adjustments (clinic_id, branch_id, product_id, delta, reason, adjusted_by_user_id, warehouse_id) "
            "VALUES (:clinic_id, :branch_id, :product_id, :delta, :reason, :user_id, :warehouse_id)"
        ), {"clinic_id": session["clinic_id"], "branch_id": dest_branch_id, "product_id": tl["product_id"],
            "delta": recv_line.quantity_received, "reason": f"Transfer in {tf['transfer_number']}",
            "user_id": session["user_id"], "warehouse_id": dest_warehouse_id})
    db.execute(text(
        "UPDATE inventory_transfers SET status = 'received', received_by_user_id = :user_id, received_at = now(), "
        "version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :id"
    ), {"clinic_id": session["clinic_id"], "id": transfer_id, "user_id": session["user_id"]})
    if tf["initiated_by_user_id"] != session["user_id"]:
        db.execute(text("""
            INSERT INTO notifications (clinic_id, user_id, kind, title, body)
            VALUES (:clinic_id, :user_id, 'transfer.received', 'Transfer received', :body)
        """), {"clinic_id": session["clinic_id"], "user_id": tf["initiated_by_user_id"],
               "body": f"Transfer {tf['transfer_number']} has been received and checked."})
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"],
                 action="inventory.transfer.receive", entity_type="inventory_transfer", entity_id=transfer_id,
                 outcome="success", request_id=UUID(request.state.request_id),
                 metadata={"transfer_number": tf["transfer_number"], "lines_checked": len(payload.lines)})
    db.commit()
    return {"data": {"id": transfer_id, "status": "received"}, "meta": {"request_id": request.state.request_id}}


@router.post("/{transfer_id}/cancel")
def transfer_cancel(
    transfer_id: UUID, payload: TransferCancel, request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    session = _write_authorized(db, request, session_token, "transfer.manage", csrf_token)
    tf = db.execute(text(
        "SELECT id, status, version FROM inventory_transfers WHERE clinic_id = :clinic_id AND id = :id"
    ), {"clinic_id": session["clinic_id"], "id": transfer_id}).mappings().one_or_none()
    if tf is None:
        raise _error("NOT_FOUND", "Transfer not found.", status.HTTP_404_NOT_FOUND)
    if tf["status"] == "received":
        raise _error("INVALID_INPUT", "Cannot cancel a received transfer.", status.HTTP_409_CONFLICT)
    if tf["status"] == "cancelled":
        raise _error("INVALID_INPUT", "Transfer is already cancelled.", status.HTTP_409_CONFLICT)
    if tf["version"] != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The transfer changed before this update.", status.HTTP_409_CONFLICT)
    db.execute(text(
        "UPDATE inventory_transfers SET status = 'cancelled', cancelled_by_user_id = :user_id, cancelled_at = now(), "
        "cancel_reason = :reason, version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :id"
    ), {"clinic_id": session["clinic_id"], "id": transfer_id, "user_id": session["user_id"], "reason": payload.reason})
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"],
                 action="inventory.transfer.cancel", entity_type="inventory_transfer", entity_id=transfer_id,
                 outcome="success", request_id=UUID(request.state.request_id),
                 metadata={"reason": payload.reason})
    db.commit()
    return {"data": {"id": transfer_id, "status": "cancelled"}, "meta": {"request_id": request.state.request_id}}

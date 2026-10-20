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
from app.modules.inventory.schemas import PurchaseOrderCreate, PurchaseOrderReceive, PurchaseOrderUpdate

router = APIRouter(prefix="/api/v1/purchases", tags=["purchases"])


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


def _next_po_number(db: Session, clinic_id: UUID) -> str:
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(CAST(:key AS text), 0))"),
               {"key": f"po-seq:{clinic_id}"})
    row = db.execute(text(
        "INSERT INTO po_number_sequences (clinic_id, next_value) VALUES (:clinic_id, 2) "
        "ON CONFLICT (clinic_id) DO UPDATE SET next_value = po_number_sequences.next_value + 1 "
        "RETURNING next_value - 1 AS seq"
    ), {"clinic_id": clinic_id}).mappings().one()
    return f"PO-{row['seq']:04d}"


@router.get("")
def purchase_list(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    supplier_id: UUID | None = Query(default=None),
    cursor: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
) -> dict:
    session = _authorized(db, session_token, "purchase.read")
    values = decode_cursor(cursor, "purchases") if cursor else {}
    if cursor and values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    values = values or {}
    rows = db.execute(text("""
        SELECT po.id, po.order_number, po.supplier_id, s.name AS supplier_name,
               po.warehouse_id, w.name AS warehouse_name,
               po.status, po.total_minor, po.currency, po.notes,
               po.ordered_at, po.received_at, po.version, po.created_at,
               (SELECT COUNT(*) FROM purchase_order_lines l WHERE l.clinic_id = po.clinic_id AND l.purchase_order_id = po.id) AS line_count
        FROM purchase_orders po
        JOIN suppliers s ON s.clinic_id = po.clinic_id AND s.id = po.supplier_id
        JOIN warehouses w ON w.clinic_id = po.clinic_id AND w.id = po.warehouse_id
        WHERE po.clinic_id = :clinic_id
          AND (:status IS NULL OR po.status = :status)
          AND (:supplier_id IS NULL OR po.supplier_id = :supplier_id)
          AND (:after_created IS NULL OR po.created_at < CAST(:after_created AS timestamptz)
               OR (po.created_at = CAST(:after_created AS timestamptz) AND po.id < CAST(:after_id AS uuid)))
        ORDER BY po.created_at DESC, po.id DESC LIMIT :page_size
    """), {
        "clinic_id": session["clinic_id"], "status": status_filter, "supplier_id": supplier_id,
        "after_created": values.get("created_at"), "after_id": values.get("id"), "page_size": limit + 1,
    }).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor("purchases", {"created_at": str(rows[-1]["created_at"]), "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor}}


@router.post("", status_code=status.HTTP_201_CREATED)
def purchase_create(
    payload: PurchaseOrderCreate, request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    session = _write_authorized(db, request, session_token, "purchase.manage", csrf_token)
    supplier = db.execute(text("SELECT id FROM suppliers WHERE clinic_id = :clinic_id AND id = :id AND status = 'active'"),
                          {"clinic_id": session["clinic_id"], "id": payload.supplier_id}).scalar_one_or_none()
    if supplier is None:
        raise _error("NOT_FOUND", "Supplier not found or inactive.", status.HTTP_400_BAD_REQUEST)
    warehouse = db.execute(text("SELECT id FROM warehouses WHERE clinic_id = :clinic_id AND id = :id AND status = 'active'"),
                           {"clinic_id": session["clinic_id"], "id": payload.warehouse_id}).scalar_one_or_none()
    if warehouse is None:
        raise _error("NOT_FOUND", "Warehouse not found or inactive.", status.HTTP_400_BAD_REQUEST)
    for line in payload.lines:
        product = db.execute(text("SELECT id FROM inventory_products WHERE clinic_id = :clinic_id AND id = :id AND status = 'active' AND archived_at IS NULL"),
                             {"clinic_id": session["clinic_id"], "id": line.product_id}).scalar_one_or_none()
        if product is None:
            raise _error("NOT_FOUND", f"Product {line.product_id} not found or inactive.", status.HTTP_400_BAD_REQUEST)
    order_number = _next_po_number(db, session["clinic_id"])
    total_minor = sum(int(line.quantity_ordered * line.unit_cost_minor) for line in payload.lines)
    po = db.execute(text("""
        INSERT INTO purchase_orders (clinic_id, order_number, supplier_id, warehouse_id, status, total_minor, currency, notes, ordered_by_user_id)
        VALUES (:clinic_id, :order_number, :supplier_id, :warehouse_id, 'draft', :total_minor, 'PKR', :notes, :user_id)
        RETURNING id, order_number, supplier_id, warehouse_id, status, total_minor, currency, notes, version, created_at
    """), {"clinic_id": session["clinic_id"], "order_number": order_number, "supplier_id": payload.supplier_id,
           "warehouse_id": payload.warehouse_id, "total_minor": total_minor, "notes": payload.notes,
           "user_id": session["user_id"]}).mappings().one()
    lines_out = []
    for line in payload.lines:
        l_row = db.execute(text("""
            INSERT INTO purchase_order_lines (clinic_id, purchase_order_id, product_id, quantity_ordered, unit_cost_minor)
            VALUES (:clinic_id, :po_id, :product_id, :quantity_ordered, :unit_cost_minor)
            RETURNING id, product_id, quantity_ordered, quantity_received, unit_cost_minor, currency
        """), {"clinic_id": session["clinic_id"], "po_id": po["id"], "product_id": line.product_id,
               "quantity_ordered": line.quantity_ordered, "unit_cost_minor": line.unit_cost_minor}).mappings().one()
        lines_out.append(dict(l_row))
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"],
                 action="inventory.purchase.create", entity_type="purchase_order", entity_id=po["id"],
                 outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": {**dict(po), "lines": lines_out}, "meta": {"request_id": request.state.request_id}}


@router.get("/{purchase_id}")
def purchase_detail(
    purchase_id: UUID, request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
) -> dict:
    session = _authorized(db, session_token, "purchase.read")
    po = db.execute(text("""
        SELECT po.id, po.order_number, po.supplier_id, s.name AS supplier_name,
               po.warehouse_id, w.name AS warehouse_name, w.branch_id,
               po.status, po.total_minor, po.currency, po.notes,
               po.ordered_by_user_id, u.display_name AS ordered_by_name,
               po.ordered_at, po.received_at, po.version, po.created_at, po.updated_at
        FROM purchase_orders po
        JOIN suppliers s ON s.clinic_id = po.clinic_id AND s.id = po.supplier_id
        JOIN warehouses w ON w.clinic_id = po.clinic_id AND w.id = po.warehouse_id
        JOIN users u ON u.clinic_id = po.clinic_id AND u.id = po.ordered_by_user_id
        WHERE po.clinic_id = :clinic_id AND po.id = :id
    """), {"clinic_id": session["clinic_id"], "id": purchase_id}).mappings().one_or_none()
    if po is None:
        raise _error("NOT_FOUND", "Purchase order not found.", status.HTTP_404_NOT_FOUND)
    lines = db.execute(text("""
        SELECT l.id, l.product_id, p.name AS product_name, p.sku, p.unit,
               l.quantity_ordered, l.quantity_received, l.unit_cost_minor, l.currency
        FROM purchase_order_lines l
        JOIN inventory_products p ON p.clinic_id = l.clinic_id AND p.id = l.product_id
        WHERE l.clinic_id = :clinic_id AND l.purchase_order_id = :po_id
    """), {"clinic_id": session["clinic_id"], "po_id": purchase_id}).mappings().all()
    db.commit()
    return {"data": {**dict(po), "lines": [dict(l) for l in lines]}, "meta": {"request_id": request.state.request_id}}


@router.post("/{purchase_id}/order")
def purchase_order_confirm(
    purchase_id: UUID, request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    session = _write_authorized(db, request, session_token, "purchase.manage", csrf_token)
    row = db.execute(text(
        "UPDATE purchase_orders SET status = 'ordered', ordered_at = now(), version = version + 1, updated_at = now() "
        "WHERE clinic_id = :clinic_id AND id = :id AND status = 'draft' "
        "RETURNING id, order_number, status, ordered_at, version"
    ), {"clinic_id": session["clinic_id"], "id": purchase_id}).mappings().one_or_none()
    if row is None:
        raise _error("INVALID_INPUT", "Purchase order not found or not in draft status.", status.HTTP_409_CONFLICT)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"],
                 action="inventory.purchase.order", entity_type="purchase_order", entity_id=purchase_id,
                 outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.post("/{purchase_id}/receive")
def purchase_receive(
    purchase_id: UUID, payload: PurchaseOrderReceive, request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    session = _write_authorized(db, request, session_token, "purchase.manage", csrf_token)
    po = db.execute(text("""
        SELECT po.id, po.status, po.version, w.branch_id, po.order_number
        FROM purchase_orders po
        JOIN warehouses w ON w.clinic_id = po.clinic_id AND w.id = po.warehouse_id
        WHERE po.clinic_id = :clinic_id AND po.id = :id
    """), {"clinic_id": session["clinic_id"], "id": purchase_id}).mappings().one_or_none()
    if po is None:
        raise _error("NOT_FOUND", "Purchase order not found.", status.HTTP_404_NOT_FOUND)
    if po["status"] not in ("ordered", "partially_received"):
        raise _error("INVALID_INPUT", "Purchase order must be ordered or partially received to receive goods.", status.HTTP_409_CONFLICT)
    if po["version"] != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The purchase order changed before this update.", status.HTTP_409_CONFLICT)
    branch_id = po["branch_id"]
    for recv_line in payload.lines:
        po_line = db.execute(text(
            "SELECT id, product_id, quantity_ordered, quantity_received FROM purchase_order_lines "
            "WHERE clinic_id = :clinic_id AND id = :line_id AND purchase_order_id = :po_id"
        ), {"clinic_id": session["clinic_id"], "line_id": recv_line.line_id, "po_id": purchase_id}).mappings().one_or_none()
        if po_line is None:
            raise _error("NOT_FOUND", f"Purchase order line {recv_line.line_id} not found.", status.HTTP_400_BAD_REQUEST)
        new_received = po_line["quantity_received"] + recv_line.quantity_received
        db.execute(text("UPDATE purchase_order_lines SET quantity_received = :qty WHERE clinic_id = :clinic_id AND id = :id"),
                   {"clinic_id": session["clinic_id"], "id": recv_line.line_id, "qty": new_received})
        if recv_line.quantity_received > 0:
            stock = db.execute(text(
                "SELECT id, quantity FROM inventory_stock WHERE clinic_id = :clinic_id AND branch_id = :branch_id AND product_id = :product_id FOR UPDATE"
            ), {"clinic_id": session["clinic_id"], "branch_id": branch_id, "product_id": po_line["product_id"]}).mappings().one_or_none()
            if stock is None:
                db.execute(text(
                    "INSERT INTO inventory_stock (clinic_id, branch_id, product_id, quantity) VALUES (:clinic_id, :branch_id, :product_id, :qty)"
                ), {"clinic_id": session["clinic_id"], "branch_id": branch_id, "product_id": po_line["product_id"], "qty": recv_line.quantity_received})
            else:
                db.execute(text(
                    "UPDATE inventory_stock SET quantity = quantity + :qty, version = version + 1, updated_at = now() "
                    "WHERE clinic_id = :clinic_id AND id = :id"
                ), {"clinic_id": session["clinic_id"], "id": stock["id"], "qty": recv_line.quantity_received})
            db.execute(text(
                "INSERT INTO inventory_adjustments (clinic_id, branch_id, product_id, delta, reason, adjusted_by_user_id) "
                "VALUES (:clinic_id, :branch_id, :product_id, :delta, :reason, :user_id)"
            ), {"clinic_id": session["clinic_id"], "branch_id": branch_id, "product_id": po_line["product_id"],
                "delta": recv_line.quantity_received, "reason": f"Purchase order {po['order_number']}",
                "user_id": session["user_id"]})
    all_lines = db.execute(text(
        "SELECT quantity_ordered, quantity_received FROM purchase_order_lines WHERE clinic_id = :clinic_id AND purchase_order_id = :po_id"
    ), {"clinic_id": session["clinic_id"], "po_id": purchase_id}).mappings().all()
    fully_received = all(l["quantity_received"] >= l["quantity_ordered"] for l in all_lines)
    new_status = "received" if fully_received else "partially_received"
    db.execute(text(
        "UPDATE purchase_orders SET status = :status, received_at = CASE WHEN :status = 'received' THEN now() ELSE received_at END, "
        "version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :id"
    ), {"clinic_id": session["clinic_id"], "id": purchase_id, "status": new_status})
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"],
                 action="inventory.purchase.receive", entity_type="purchase_order", entity_id=purchase_id,
                 outcome="success", request_id=UUID(request.state.request_id),
                 metadata={"new_status": new_status, "lines_received": len(payload.lines)})
    db.commit()
    return {"data": {"id": purchase_id, "status": new_status, "fully_received": fully_received}, "meta": {"request_id": request.state.request_id}}


@router.post("/{purchase_id}/cancel")
def purchase_cancel(
    purchase_id: UUID, request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    session = _write_authorized(db, request, session_token, "purchase.manage", csrf_token)
    row = db.execute(text(
        "UPDATE purchase_orders SET status = 'cancelled', version = version + 1, updated_at = now() "
        "WHERE clinic_id = :clinic_id AND id = :id AND status NOT IN ('received', 'cancelled') "
        "RETURNING id, order_number, status, version"
    ), {"clinic_id": session["clinic_id"], "id": purchase_id}).mappings().one_or_none()
    if row is None:
        raise _error("INVALID_INPUT", "Purchase order not found or already completed/cancelled.", status.HTTP_409_CONFLICT)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"],
                 action="inventory.purchase.cancel", entity_type="purchase_order", entity_id=purchase_id,
                 outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}

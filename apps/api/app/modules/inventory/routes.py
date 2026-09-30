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
from app.modules.inventory.schemas import InventoryAdjustmentCreate, InventoryProductCreate, InventoryProductUpdate, InventoryStatusUpdate

router = APIRouter(prefix="/api/v1/inventory", tags=["inventory"])


def _authorized(db: Session, session_token: str | None, permission: str, branch_id: UUID | None = None) -> dict:
    session = _session_or_401(db, session_token)
    if session["clinic_id"] is None:
        raise _error("FORBIDDEN", "A clinic context is required.", status.HTTP_403_FORBIDDEN)
    set_tenant_context(db, session["clinic_id"], session["user_id"])
    try:
        require_permission(db, session["user_id"], session["clinic_id"], permission, branch_id=branch_id)
    except ForbiddenError as exc:
        raise _error("FORBIDDEN", "You do not have permission for this inventory operation.", status.HTTP_403_FORBIDDEN) from exc
    return session


def _write_authorized(db: Session, request: Request, session_token: str | None, permission: str, csrf_token: str | None, branch_id: UUID | None = None) -> dict:
    _validate_origin(request)
    session = _authorized(db, session_token, permission, branch_id=branch_id)
    if not csrf_token:
        raise _error("CSRF_REQUIRED", "A CSRF token is required.", status.HTTP_403_FORBIDDEN)
    try:
        verify_csrf(session, csrf_token)
    except SessionError as exc:
        raise _error("CSRF_INVALID", "The CSRF token is invalid.", status.HTTP_403_FORBIDDEN) from exc
    return session


@router.get("/products")
def product_list(request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "inventory.read")
    values = decode_cursor(cursor, "inventory-products") if cursor else {}
    if cursor and values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    values = values or {}
    rows = db.execute(text("""
        SELECT id, sku, name, product_type, unit, minimum_stock, status, version, created_at, updated_at
        FROM inventory_products
        WHERE clinic_id = :clinic_id AND archived_at IS NULL
          AND (:after_name IS NULL OR name > :after_name OR (name = :after_name AND id > CAST(:after_id AS uuid)))
        ORDER BY name, id LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "after_name": values.get("name"), "after_id": values.get("id"), "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit; rows = rows[:limit]
    next_cursor = encode_cursor("inventory-products", {"name": rows[-1]["name"], "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor}}


@router.post("/products", status_code=status.HTTP_201_CREATED)
def product_create(payload: InventoryProductCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "inventory.manage", csrf_token)
    try:
        row = db.execute(text("""
            INSERT INTO inventory_products (clinic_id, sku, name, product_type, unit, minimum_stock)
            VALUES (:clinic_id, :sku, :name, :product_type, :unit, :minimum_stock)
            RETURNING id, sku, name, product_type, unit, minimum_stock, status, version, created_at
        """), {"clinic_id": session["clinic_id"], **payload.model_dump()}).mappings().one()
    except Exception as exc:
        db.rollback()
        if "uq_inventory_products_sku" in str(exc):
            raise _error("DUPLICATE", "A product with this SKU already exists.", status.HTTP_409_CONFLICT) from exc
        raise
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="inventory.product.create", entity_type="inventory_product", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.patch("/products/{product_id}")
def product_update(product_id: UUID, payload: InventoryProductUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "inventory.manage", csrf_token)
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    if not values:
        raise _error("INVALID_INPUT", "At least one product field must be provided.", status.HTTP_400_BAD_REQUEST)
    assignments = ", ".join(f"{field} = :{field}" for field in values)
    try:
        row = db.execute(text(f"UPDATE inventory_products SET {assignments}, version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL AND version = :expected_version RETURNING id, sku, name, product_type, unit, minimum_stock, status, version, updated_at"), {"clinic_id": session["clinic_id"], "id": product_id, "expected_version": payload.expected_version, **values}).mappings().one_or_none()
    except Exception as exc:
        db.rollback()
        if "uq_inventory_products_sku" in str(exc):
            raise _error("DUPLICATE", "A product with this SKU already exists.", status.HTTP_409_CONFLICT) from exc
        raise
    if row is None:
        raise _error("VERSION_CONFLICT", "The product changed before this update.", status.HTTP_409_CONFLICT)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="inventory.product.update", entity_type="inventory_product", entity_id=product_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"fields": sorted(values)})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.post("/products/{product_id}/status")
def product_status(product_id: UUID, payload: InventoryStatusUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "inventory.manage", csrf_token)
    row = db.execute(text("UPDATE inventory_products SET status = :status, archived_at = CASE WHEN :status = 'archived' THEN COALESCE(archived_at, now()) ELSE NULL END, version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :id RETURNING id, name, status, version, archived_at, updated_at"), {"clinic_id": session["clinic_id"], "id": product_id, "status": payload.status}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Inventory product not found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="inventory.product.status", entity_type="inventory_product", entity_id=product_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"status": payload.status})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.get("/stock")
def stock_list(request: Request, branch_id: UUID | None = Query(default=None), low_only: bool = Query(default=False), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "inventory.read", branch_id=branch_id)
    rows = db.execute(text("""
        SELECT stock.id, stock.branch_id, b.name AS branch_name, stock.product_id, p.name AS product_name,
               p.product_type, p.unit, p.minimum_stock, stock.quantity, stock.version, stock.updated_at,
               (stock.quantity <= p.minimum_stock) AS low_stock
        FROM inventory_stock stock
        JOIN inventory_products p ON p.clinic_id = stock.clinic_id AND p.id = stock.product_id
        JOIN branches b ON b.clinic_id = stock.clinic_id AND b.id = stock.branch_id
        WHERE stock.clinic_id = :clinic_id AND p.archived_at IS NULL
          AND (:branch_id IS NULL OR stock.branch_id = :branch_id)
          AND (NOT :low_only OR stock.quantity <= p.minimum_stock)
          AND (NOT EXISTS (SELECT 1 FROM user_branch_scopes scope WHERE scope.clinic_id = :clinic_id AND scope.user_id = :user_id)
               OR EXISTS (SELECT 1 FROM user_branch_scopes scope WHERE scope.clinic_id = :clinic_id AND scope.user_id = :user_id AND scope.branch_id = stock.branch_id))
        ORDER BY low_stock DESC, p.name, stock.branch_id
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "branch_id": branch_id, "low_only": low_only}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.post("/adjustments", status_code=status.HTTP_201_CREATED)
def stock_adjust(payload: InventoryAdjustmentCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, "inventory.manage", csrf_token, branch_id=payload.branch_id)
    product = db.execute(text("SELECT id FROM inventory_products WHERE clinic_id = :clinic_id AND id = :product_id AND status = 'active' AND archived_at IS NULL"), {"clinic_id": session["clinic_id"], "product_id": payload.product_id}).scalar_one_or_none()
    if product is None:
        raise _error("NOT_FOUND", "Inventory product not found.", status.HTTP_404_NOT_FOUND)
    stock = db.execute(text("SELECT id, quantity, version FROM inventory_stock WHERE clinic_id = :clinic_id AND branch_id = :branch_id AND product_id = :product_id FOR UPDATE"), {"clinic_id": session["clinic_id"], "branch_id": payload.branch_id, "product_id": payload.product_id}).mappings().one_or_none()
    if stock is None:
        if payload.delta < 0:
            raise _error("INSUFFICIENT_STOCK", "This branch has no available stock to remove.", status.HTTP_409_CONFLICT)
        stock_id = db.execute(text("INSERT INTO inventory_stock (clinic_id, branch_id, product_id, quantity) VALUES (:clinic_id, :branch_id, :product_id, :quantity) RETURNING id"), {"clinic_id": session["clinic_id"], "branch_id": payload.branch_id, "product_id": payload.product_id, "quantity": payload.delta}).scalar_one()
        new_quantity = payload.delta
    else:
        new_quantity = stock["quantity"] + payload.delta
        if new_quantity < 0:
            raise _error("INSUFFICIENT_STOCK", "The adjustment would make stock negative.", status.HTTP_409_CONFLICT)
        stock_id = stock["id"]
        db.execute(text("UPDATE inventory_stock SET quantity = :quantity, version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :id"), {"clinic_id": session["clinic_id"], "id": stock_id, "quantity": new_quantity})
    adjustment = db.execute(text("INSERT INTO inventory_adjustments (clinic_id, branch_id, product_id, delta, reason, adjusted_by_user_id) VALUES (:clinic_id, :branch_id, :product_id, :delta, :reason, :user_id) RETURNING id, branch_id, product_id, delta, reason, created_at"), {"clinic_id": session["clinic_id"], "branch_id": payload.branch_id, "product_id": payload.product_id, "delta": payload.delta, "reason": payload.reason.strip(), "user_id": session["user_id"]}).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="inventory.stock.adjust", entity_type="inventory_adjustment", entity_id=adjustment["id"], outcome="success", request_id=UUID(request.state.request_id), metadata={"branch_id": str(payload.branch_id), "product_id": str(payload.product_id), "delta": str(payload.delta), "new_quantity": str(new_quantity)})
    db.commit()
    return {"data": {**dict(adjustment), "stock_id": stock_id, "quantity": new_quantity}, "meta": {"request_id": request.state.request_id}}

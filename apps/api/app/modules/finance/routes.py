from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.audit.service import record_event
from app.modules.blueprint_core.routes import _authorized, _write_authorized, invoice_receipt
from app.modules.finance.receipt import render_html, render_pdf
from app.modules.finance.commissions import commission_minor, provider_revenue
from app.modules.finance.schemas import CommissionRuleUpdate, ExpenseCreate, ExpenseVoid
from app.modules.identity.routes import _error

router = APIRouter(prefix="/api/v1/finance", tags=["finance"])
receipt_router = APIRouter(prefix="/api/v1/invoices", tags=["billing"])


def _receipt_data(invoice_id: UUID, request: Request, db: Session, session_token: str | None) -> dict:
    return invoice_receipt(invoice_id, request, db, session_token)["data"]


@receipt_router.get("/{invoice_id}/receipt.pdf")
def receipt_pdf(invoice_id: UUID, request: Request, format: Literal["a4", "thermal"] = Query(default="a4"), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> Response:
    data = _receipt_data(invoice_id, request, db, session_token)
    filename = f"{data['invoice']['invoice_number']}-{format}.pdf".replace("/", "-")
    return Response(render_pdf(data, format), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{filename}"', "Cache-Control": "private, no-store"})


@receipt_router.get("/{invoice_id}/receipt.html")
def receipt_html(invoice_id: UUID, request: Request, format: Literal["a4", "thermal"] = Query(default="a4"), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> Response:
    data = _receipt_data(invoice_id, request, db, session_token)
    return Response(render_html(data, format), media_type="text/html; charset=utf-8", headers={"Cache-Control": "private, no-store", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})


@router.get("/cashier-summary")
def cashier_summary(request: Request, day: date | None = Query(default=None, alias="date"), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "billing.read")
    params = {"clinic_id": session["clinic_id"], "day": day}
    tz_day = "(now() AT TIME ZONE c.timezone)::date"
    methods = db.execute(text(f"""
        SELECT p.method, COUNT(*) AS payments, COALESCE(SUM(p.amount_minor), 0) AS collected_minor
        FROM payments p JOIN clinics c ON c.id = p.clinic_id
        WHERE p.clinic_id = :clinic_id AND (p.paid_at AT TIME ZONE c.timezone)::date = COALESCE(:day, {tz_day})
        GROUP BY p.method ORDER BY collected_minor DESC, p.method
    """), params).mappings().all()
    invoiced = db.execute(text(f"""
        SELECT COUNT(*) AS invoices, COALESCE(SUM(i.total_minor), 0) AS invoiced_minor
        FROM invoices i JOIN clinics c ON c.id = i.clinic_id
        WHERE i.clinic_id = :clinic_id AND i.status <> 'void' AND (i.issued_at AT TIME ZONE c.timezone)::date = COALESCE(:day, {tz_day})
    """), params).mappings().one()
    try:
        _authorized(db, session_token, "expense.read")
        spent = db.execute(text(f"""
            SELECT COALESCE(SUM(e.amount_minor), 0)
            FROM expenses e JOIN clinics c ON c.id = e.clinic_id
            WHERE e.clinic_id = :clinic_id AND e.voided_at IS NULL AND e.incurred_on = COALESCE(:day, {tz_day})
        """), params).scalar_one()
    except HTTPException:  # expense.read is optional for cashiers
        spent = None
    resolved_day = day or db.execute(text("SELECT (now() AT TIME ZONE timezone)::date FROM clinics WHERE id = :clinic_id"), params).scalar_one()
    collected = sum(row["collected_minor"] for row in methods)
    db.commit()
    return {"data": {"date": resolved_day.isoformat(), "payment_methods": [dict(row) for row in methods], "collected_minor": collected, "invoices": invoiced["invoices"], "invoiced_minor": invoiced["invoiced_minor"], "expenses_minor": spent, "net_minor": None if spent is None else collected - spent}, "meta": {"request_id": request.state.request_id}}


@router.get("/expenses")
def expense_list(request: Request, start: date | None = Query(default=None), end: date | None = Query(default=None), limit: int = Query(default=100, ge=1, le=200), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "expense.read")
    rows = db.execute(text("""
        SELECT id, branch_id, category, description, amount_minor, currency, incurred_on, voided_at, void_reason, created_at
        FROM expenses
        WHERE clinic_id = :clinic_id AND (CAST(:start AS date) IS NULL OR incurred_on >= :start) AND (CAST(:end AS date) IS NULL OR incurred_on <= :end)
        ORDER BY incurred_on DESC, created_at DESC LIMIT :limit
    """), {"clinic_id": session["clinic_id"], "start": start, "end": end, "limit": limit}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.post("/expenses", status_code=status.HTTP_201_CREATED)
def expense_create(payload: ExpenseCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "expense.manage", csrf_token)
    row = db.execute(text("""
        INSERT INTO expenses (clinic_id, branch_id, category, description, amount_minor, currency, incurred_on, recorded_by_user_id)
        VALUES (:clinic_id, :branch_id, :category, :description, :amount_minor, :currency, :incurred_on, :user_id)
        RETURNING id, branch_id, category, description, amount_minor, currency, incurred_on, voided_at, created_at
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], **payload.model_dump()}).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="expense.create", entity_type="expense", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id), metadata={"amount_minor": payload.amount_minor, "category": payload.category})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.post("/expenses/{expense_id}/void")
def expense_void(expense_id: UUID, payload: ExpenseVoid, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "expense.manage", csrf_token)
    row = db.execute(text("""
        UPDATE expenses SET voided_at = now(), void_reason = :reason
        WHERE clinic_id = :clinic_id AND id = :expense_id AND voided_at IS NULL
        RETURNING id, voided_at, void_reason
    """), {"clinic_id": session["clinic_id"], "expense_id": expense_id, "reason": payload.reason}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "The expense was not found or is already void.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="expense.void", entity_type="expense", entity_id=expense_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"reason": payload.reason})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.get("/commission-rules")
def commission_rules(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "billing.read")
    rows = db.execute(text("""
        SELECT d.id AS doctor_id, d.public_name, COALESCE(r.percent_bp, 0) AS percent_bp, COALESCE(r.active, false) AS active
        FROM doctor_profiles d LEFT JOIN provider_commission_rules r ON r.clinic_id = d.clinic_id AND r.doctor_id = d.id
        WHERE d.clinic_id = :c AND d.archived_at IS NULL ORDER BY d.public_name LIMIT 200
    """), {"c": session["clinic_id"]}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.put("/commission-rules/{doctor_id}")
def commission_rule_set(doctor_id: UUID, payload: CommissionRuleUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "billing.manage", csrf_token)
    try:
        row = db.execute(text("""
            INSERT INTO provider_commission_rules (clinic_id, doctor_id, percent_bp, active, updated_by)
            VALUES (:c, :doctor_id, :percent_bp, :active, :user)
            ON CONFLICT (clinic_id, doctor_id) DO UPDATE SET percent_bp = EXCLUDED.percent_bp, active = EXCLUDED.active, updated_by = EXCLUDED.updated_by, updated_at = now()
            RETURNING doctor_id, percent_bp, active
        """), {"c": session["clinic_id"], "doctor_id": doctor_id, "percent_bp": payload.percent_bp, "active": payload.active, "user": session["user_id"]}).mappings().one()
    except IntegrityError as exc:
        db.rollback()
        raise _error("NOT_FOUND", "That provider does not exist in this clinic.", status.HTTP_404_NOT_FOUND) from exc
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="commission.rule.set", entity_type="provider_commission_rule", entity_id=doctor_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"percent_bp": payload.percent_bp, "active": payload.active})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.get("/provider-revenue")
def provider_revenue_report(request: Request, start: date = Query(), end: date = Query(), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    """Cash-basis revenue per provider for payments received in [start, end], plus commission where a rule is active."""
    session = _authorized(db, session_token, "billing.read")
    if end < start or (end - start).days > 366:
        raise _error("INVALID_INPUT", "Choose a range of at most one year with the end on or after the start.", status.HTTP_400_BAD_REQUEST)
    params = {"c": session["clinic_id"], "start": start, "end": end}
    allocations = db.execute(text("""
        SELECT pa.invoice_id, SUM(pa.amount_minor)::bigint AS amount
        FROM payment_allocations pa JOIN payments p ON p.clinic_id = pa.clinic_id AND p.id = pa.payment_id
        WHERE pa.clinic_id = :c AND p.paid_at >= :start AND p.paid_at < CAST(:end AS date) + 1
        GROUP BY pa.invoice_id
    """), params).mappings().all()
    invoice_ids = [row["invoice_id"] for row in allocations]
    line_totals: dict = {}
    if invoice_ids:
        for row in db.execute(text("SELECT invoice_id, provider_id, SUM(line_total_minor)::bigint AS total FROM invoice_lines WHERE clinic_id = :c AND invoice_id = ANY(:ids) GROUP BY invoice_id, provider_id"), {"c": session["clinic_id"], "ids": invoice_ids}).mappings().all():
            line_totals.setdefault(row["invoice_id"], {})[row["provider_id"]] = row["total"]
    revenue = provider_revenue([(row["invoice_id"], row["amount"]) for row in allocations], line_totals)
    providers = {row["id"]: row for row in db.execute(text("""
        SELECT d.id, d.public_name, r.percent_bp, COALESCE(r.active, false) AS active
        FROM doctor_profiles d LEFT JOIN provider_commission_rules r ON r.clinic_id = d.clinic_id AND r.doctor_id = d.id WHERE d.clinic_id = :c
    """), {"c": session["clinic_id"]}).mappings().all()}
    rows = []
    for provider_id, amount in sorted(revenue.items(), key=lambda item: -item[1]):
        info = providers.get(provider_id)
        rows.append({"provider_id": provider_id, "provider_name": info["public_name"] if info else "Unassigned", "revenue_minor": amount, "percent_bp": info["percent_bp"] if info else None, "commission_minor": commission_minor(amount, info["percent_bp"], info["active"]) if info else 0})
    db.commit()
    return {"data": {"start": start.isoformat(), "end": end.isoformat(), "providers": rows, "total_revenue_minor": sum(revenue.values()), "total_commission_minor": sum(row["commission_minor"] for row in rows)}, "meta": {"request_id": request.state.request_id}}

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import decode_cursor, encode_cursor
from app.db.session import get_db
from app.db.tenant import set_tenant_context
from app.modules.audit.service import record_event
from app.modules.authorization.service import ForbiddenError, require_permission
from app.modules.blueprint_core.schemas import (
    InvoiceCreate,
    LeadActivityCreate,
    LeadConvert,
    LeadCreate,
    LeadUpdate,
    PaymentCreate,
    SpecialtyEnable,
)
from app.modules.crm.routes import _normalize_email, _normalize_phone
from app.modules.identity.routes import _error, _session_or_401, _validate_origin
from app.modules.identity.service import SessionError, verify_csrf


specialty_router = APIRouter(prefix="/api/v1/specialties", tags=["specialties"])
lead_router = APIRouter(prefix="/api/v1/leads", tags=["leads"])
billing_router = APIRouter(prefix="/api/v1/invoices", tags=["billing"])


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


@specialty_router.get("")
def specialty_list(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "specialty.read")
    rows = db.execute(text("""
        SELECT s.id, s.code, s.name, s.description, cs.status, cs.enabled_at, cs.version
        FROM clinic_specialties cs JOIN specialties s ON s.id = cs.specialty_id
        WHERE cs.clinic_id = :clinic_id AND cs.archived_at IS NULL AND s.status = 'active'
        ORDER BY s.name, s.id
    """), {"clinic_id": session["clinic_id"]}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@specialty_router.get("/library")
def specialty_library(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "specialty.read")
    rows = db.execute(text("""
        SELECT s.id, s.code, s.name, s.description,
               EXISTS (SELECT 1 FROM clinic_specialties cs WHERE cs.clinic_id = :clinic_id AND cs.specialty_id = s.id AND cs.status = 'active' AND cs.archived_at IS NULL) AS enabled
        FROM specialties s WHERE s.status = 'active' ORDER BY s.name, s.id
    """), {"clinic_id": session["clinic_id"]}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@specialty_router.post("/enable", status_code=status.HTTP_201_CREATED)
def specialty_enable(payload: SpecialtyEnable, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "specialty.manage", csrf_token)
    specialty = db.execute(text("SELECT id, code, name, description FROM specialties WHERE code = :code AND status = 'active'"), {"code": payload.code}).mappings().one_or_none()
    if specialty is None:
        raise _error("NOT_FOUND", "Specialty not found in the platform library.", status.HTTP_404_NOT_FOUND)
    try:
        row = db.execute(text("""
            INSERT INTO clinic_specialties (clinic_id, specialty_id)
            VALUES (:clinic_id, :specialty_id)
            ON CONFLICT (clinic_id, specialty_id) DO UPDATE SET status = 'active', archived_at = NULL, version = clinic_specialties.version + 1
            RETURNING clinic_id, specialty_id, status, enabled_at, version
        """), {"clinic_id": session["clinic_id"], "specialty_id": specialty["id"]}).mappings().one()
    except IntegrityError as exc:
        db.rollback()
        raise _error("CONFLICT", "The specialty could not be enabled.", status.HTTP_409_CONFLICT) from exc
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="specialty.enable", entity_type="clinic_specialty", entity_id=specialty["id"], outcome="success", request_id=UUID(request.state.request_id), metadata={"code": specialty["code"]})
    db.commit()
    return {"data": {**dict(specialty), **dict(row)}, "meta": {"request_id": request.state.request_id}}


@lead_router.get("")
def lead_list(request: Request, status_filter: str | None = Query(default=None, alias="status", max_length=40), cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "lead.read")
    values = decode_cursor(cursor, "leads") if cursor else {}
    if cursor and values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    values = values or {}
    rows = db.execute(text("""
        SELECT l.id, l.full_name, l.normalized_email, l.normalized_phone, l.source, l.campaign,
               l.status, l.specialty_id, l.requested_service_id, l.assigned_to_user_id,
               l.appointment_id, l.converted_to_patient_id, l.lost_reason, l.created_at, l.updated_at, l.version
        FROM leads l
        WHERE l.clinic_id = :clinic_id AND l.archived_at IS NULL
          AND (:status IS NULL OR l.status = :status)
          AND (:after_created_at IS NULL OR l.created_at < :after_created_at OR (l.created_at = :after_created_at AND l.id < :after_id))
        ORDER BY l.created_at DESC, l.id DESC LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "status": status_filter, "after_created_at": values.get("created_at"), "after_id": values.get("id"), "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor("leads", {"created_at": rows[-1]["created_at"].isoformat(), "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@lead_router.post("", status_code=status.HTTP_201_CREATED)
def lead_create(payload: LeadCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "lead.manage", csrf_token)
    row = db.execute(text("""
        INSERT INTO leads (clinic_id, full_name, normalized_email, normalized_phone, source, campaign, specialty_id, requested_service_id, assigned_to_user_id, notes)
        VALUES (:clinic_id, :full_name, :email, :phone, :source, :campaign, :specialty_id, :service_id, :assigned_to, :notes)
        RETURNING id, full_name, normalized_email, normalized_phone, source, campaign, specialty_id, requested_service_id, assigned_to_user_id, status, notes, version, created_at, updated_at
    """), {"clinic_id": session["clinic_id"], "full_name": payload.full_name.strip(), "email": _normalize_email(payload.email), "phone": _normalize_phone(payload.phone), "source": payload.source.strip().casefold(), "campaign": payload.campaign, "specialty_id": payload.specialty_id, "service_id": payload.requested_service_id, "assigned_to": payload.assigned_to_user_id, "notes": payload.notes}).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="lead.create", entity_type="lead", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id), metadata={"source": row["source"]})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@lead_router.patch("/{lead_id}")
def lead_update(lead_id: UUID, payload: LeadUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "lead.manage", csrf_token)
    lead = db.execute(text("""
        SELECT status, converted_to_patient_id, version FROM leads
        WHERE clinic_id = :clinic_id AND id = :lead_id AND archived_at IS NULL
        FOR UPDATE
    """), {"clinic_id": session["clinic_id"], "lead_id": lead_id}).mappings().one_or_none()
    if lead is None or lead["version"] != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The lead changed before this update or is unavailable.", status.HTTP_409_CONFLICT)
    if payload.status is not None and (
        lead["status"] == "converted" or lead["converted_to_patient_id"] is not None
    ):
        raise _error("LEAD_CONVERTED", "A converted lead cannot return to the sales pipeline.", status.HTTP_409_CONFLICT)
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    assignments = ", ".join(f"{field} = :{field}" for field in values)
    row = db.execute(text(f"""
        UPDATE leads SET {assignments}, version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :lead_id AND archived_at IS NULL AND version = :expected_version
        RETURNING id, full_name, status, assigned_to_user_id, notes, lost_reason, version, updated_at
    """), {"clinic_id": session["clinic_id"], "lead_id": lead_id, "expected_version": payload.expected_version, **values}).mappings().one_or_none()
    if row is None:
        raise _error("VERSION_CONFLICT", "The lead changed before this update or is unavailable.", status.HTTP_409_CONFLICT)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="lead.update", entity_type="lead", entity_id=lead_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"fields": sorted(values)})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


def _require_activity_lead(db: Session, session: dict, lead_id: UUID) -> None:
    lead = db.execute(text("""
        SELECT l.id FROM leads l
        WHERE l.clinic_id = :clinic_id AND l.id = :lead_id AND l.archived_at IS NULL
          AND (
            NOT EXISTS (SELECT 1 FROM user_specialty_scopes s
                        WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id)
            OR EXISTS (SELECT 1 FROM user_specialty_scopes s
                       WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id
                         AND s.specialty_id = l.specialty_id)
          )
          AND (
            NOT EXISTS (SELECT 1 FROM user_branch_scopes s
                        WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id)
            OR EXISTS (
                SELECT 1 FROM appointments a JOIN user_branch_scopes s
                  ON s.clinic_id = a.clinic_id AND s.branch_id = a.branch_id
                WHERE a.clinic_id = l.clinic_id AND a.id = l.appointment_id
                  AND s.user_id = :user_id
            )
          )
        FOR SHARE OF l
    """), {
        "clinic_id": session["clinic_id"], "user_id": session["user_id"], "lead_id": lead_id,
    }).scalar_one_or_none()
    if lead is None:
        raise _error("NOT_FOUND", "Lead not found.", status.HTTP_404_NOT_FOUND)


@lead_router.get("/{lead_id}/activities")
def lead_activity_list(
    lead_id: UUID,
    request: Request,
    cursor: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
) -> dict:
    session = _authorized(db, session_token, "lead.read")
    _require_activity_lead(db, session, lead_id)
    namespace = f"lead-activities:{session['clinic_id']}:{lead_id}"
    values = decode_cursor(cursor, namespace) if cursor else {}
    if cursor and values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    values = values or {}
    rows = db.execute(text("""
        SELECT id, lead_id, actor_user_id, kind, body, due_at, created_at
        FROM lead_activities
        WHERE clinic_id = :clinic_id AND lead_id = :lead_id
          AND (CAST(:after_created_at AS timestamptz) IS NULL
               OR created_at < CAST(:after_created_at AS timestamptz)
               OR (created_at = CAST(:after_created_at AS timestamptz)
                   AND id < CAST(:after_id AS uuid)))
        ORDER BY created_at DESC, id DESC LIMIT :page_size
    """), {
        "clinic_id": session["clinic_id"], "lead_id": lead_id,
        "after_created_at": values.get("created_at"), "after_id": values.get("id"),
        "page_size": limit + 1,
    }).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(namespace, {
        "created_at": rows[-1]["created_at"].isoformat(), "id": str(rows[-1]["id"]),
    }) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {
        "request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit,
    }}


@lead_router.post("/{lead_id}/activities", status_code=status.HTTP_201_CREATED)
def lead_activity_create(
    lead_id: UUID,
    payload: LeadActivityCreate,
    request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    session = _write_authorized(db, request, session_token, "lead.manage", csrf_token)
    _require_activity_lead(db, session, lead_id)
    row = db.execute(text("""
        INSERT INTO lead_activities (clinic_id, lead_id, actor_user_id, kind, body, due_at)
        VALUES (:clinic_id, :lead_id, :actor_user_id, :kind, :body, :due_at)
        RETURNING id, lead_id, actor_user_id, kind, body, due_at, created_at
    """), {
        "clinic_id": session["clinic_id"], "lead_id": lead_id,
        "actor_user_id": session["user_id"], **payload.model_dump(),
    }).mappings().one()
    record_event(
        db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"],
        action="lead.activity.create", entity_type="lead_activity", entity_id=row["id"],
        outcome="success", request_id=UUID(request.state.request_id),
        metadata={"lead_id": str(lead_id), "kind": payload.kind},
    )
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@lead_router.post("/{lead_id}/convert")
def lead_convert(lead_id: UUID, payload: LeadConvert, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "lead.manage", csrf_token)
    lead = db.execute(text("SELECT * FROM leads WHERE clinic_id = :clinic_id AND id = :lead_id AND archived_at IS NULL FOR UPDATE"), {"clinic_id": session["clinic_id"], "lead_id": lead_id}).mappings().one_or_none()
    if lead is None:
        raise _error("NOT_FOUND", "Lead not found.", status.HTTP_404_NOT_FOUND)
    if lead["converted_to_patient_id"] is not None:
        return {"data": {"lead_id": lead_id, "patient_id": lead["converted_to_patient_id"], "already_converted": True}, "meta": {"request_id": request.state.request_id}}
    patient_id = payload.patient_id
    if patient_id is not None:
        valid = db.execute(text("SELECT id FROM patients WHERE clinic_id = :clinic_id AND id = :patient_id AND archived_at IS NULL AND duplicate_of IS NULL"), {"clinic_id": session["clinic_id"], "patient_id": patient_id}).scalar_one_or_none()
        if valid is None:
            raise _error("NOT_FOUND", "The target patient was not found.", status.HTTP_404_NOT_FOUND)
    else:
        full_name = (payload.full_name or lead["full_name"]).strip()
        email = _normalize_email(payload.email) or lead["normalized_email"]
        phone = _normalize_phone(payload.phone) or lead["normalized_phone"]
        candidates = db.execute(text("""
            SELECT id FROM patients
            WHERE clinic_id = :clinic_id AND archived_at IS NULL AND duplicate_of IS NULL
              AND ((:email IS NOT NULL AND normalized_email = :email) OR (:phone IS NOT NULL AND normalized_phone = :phone))
            ORDER BY created_at LIMIT 2
        """), {"clinic_id": session["clinic_id"], "email": email, "phone": phone}).scalars().all()
        if len(candidates) > 1:
            raise _error("DUPLICATE_REVIEW_REQUIRED", "Review duplicate patient candidates before conversion.", status.HTTP_409_CONFLICT)
        patient_id = candidates[0] if candidates else db.execute(text("""
            INSERT INTO patients (clinic_id, patient_number, full_name, normalized_email, normalized_phone, date_of_birth)
            VALUES (:clinic_id, 'PENDING-' || substr(gen_random_uuid()::text, 1, 12), :full_name, :email, :phone, :date_of_birth)
            RETURNING id
        """), {"clinic_id": session["clinic_id"], "full_name": full_name, "email": email, "phone": phone, "date_of_birth": payload.date_of_birth}).scalar_one()
    row = db.execute(text("""
        UPDATE leads SET converted_to_patient_id = :patient_id, status = 'converted', version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :lead_id AND converted_to_patient_id IS NULL
        RETURNING id, status, converted_to_patient_id, version, updated_at
    """), {"clinic_id": session["clinic_id"], "lead_id": lead_id, "patient_id": patient_id}).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="lead.convert", entity_type="lead", entity_id=lead_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"patient_id": str(patient_id)})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@billing_router.get("")
def invoice_list(request: Request, patient_id: UUID | None = None, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "billing.read")
    values = decode_cursor(cursor, "invoices") if cursor else {}
    if cursor and values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    values = values or {}
    rows = db.execute(text("""
        SELECT i.id, i.patient_id, i.invoice_number, i.currency, i.subtotal_minor, i.discount_minor, i.tax_minor, i.total_minor,
               COALESCE((SELECT sum(pa.amount_minor) FROM payment_allocations pa WHERE pa.clinic_id = i.clinic_id AND pa.invoice_id = i.id), 0) AS paid_minor,
               i.status, i.issued_at, i.notes, i.version
        FROM invoices i
        WHERE i.clinic_id = :clinic_id AND (:patient_id IS NULL OR i.patient_id = :patient_id)
          AND (:after_issued_at IS NULL OR i.issued_at < :after_issued_at OR (i.issued_at = :after_issued_at AND i.id < :after_id))
        ORDER BY i.issued_at DESC, i.id DESC LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "after_issued_at": values.get("issued_at"), "after_id": values.get("id"), "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor("invoices", {"issued_at": rows[-1]["issued_at"].isoformat(), "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@billing_router.post("", status_code=status.HTTP_201_CREATED)
def invoice_create(payload: InvoiceCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "billing.manage", csrf_token)
    patient = db.execute(text("SELECT id FROM patients WHERE clinic_id = :clinic_id AND id = :patient_id AND archived_at IS NULL AND duplicate_of IS NULL"), {"clinic_id": session["clinic_id"], "patient_id": payload.patient_id}).scalar_one_or_none()
    if patient is None:
        raise _error("NOT_FOUND", "Patient not found.", status.HTTP_404_NOT_FOUND)
    currency = payload.currency.upper()
    subtotal = sum(line.quantity * line.unit_price_minor for line in payload.lines)
    tax = sum(line.tax_minor for line in payload.lines)
    total = subtotal - payload.discount_minor + tax
    if total < 0:
        raise _error("INVALID_INPUT", "Discount cannot exceed the line subtotal plus tax.", status.HTTP_400_BAD_REQUEST)
    sequence_year = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).year
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(CAST(:sequence_key AS text), 0))"), {"sequence_key": f"invoice-sequence:{session['clinic_id']}:{sequence_year}"})
    sequence = db.execute(text("""
        INSERT INTO invoice_number_sequences (clinic_id, sequence_year, next_value)
        VALUES (:clinic_id, :sequence_year, 2)
        ON CONFLICT (clinic_id, sequence_year) DO UPDATE SET next_value = invoice_number_sequences.next_value + 1
        RETURNING next_value - 1 AS sequence_value
    """), {"clinic_id": session["clinic_id"], "sequence_year": sequence_year}).scalar_one()
    invoice_number = f"CLINIC-{sequence_year}-{sequence:06d}"
    invoice = db.execute(text("""
        INSERT INTO invoices (clinic_id, patient_id, invoice_number, currency, subtotal_minor, discount_minor, tax_minor, total_minor, notes, created_by_user_id)
        VALUES (:clinic_id, :patient_id, :invoice_number, :currency, :subtotal, :discount, :tax, :total, :notes, :user_id)
        RETURNING id, patient_id, invoice_number, currency, subtotal_minor, discount_minor, tax_minor, total_minor, status, issued_at, version
    """), {"clinic_id": session["clinic_id"], "patient_id": payload.patient_id, "invoice_number": invoice_number, "currency": currency, "subtotal": subtotal, "discount": payload.discount_minor, "tax": tax, "total": total, "notes": payload.notes, "user_id": session["user_id"]}).mappings().one()
    for line in payload.lines:
        db.execute(text("""
            INSERT INTO invoice_lines (clinic_id, invoice_id, service_id, description, quantity, unit_price_minor, tax_minor, line_total_minor)
            VALUES (:clinic_id, :invoice_id, :service_id, :description, :quantity, :unit_price, :tax, :line_total)
        """), {"clinic_id": session["clinic_id"], "invoice_id": invoice["id"], "service_id": line.service_id, "description": line.description.strip(), "quantity": line.quantity, "unit_price": line.unit_price_minor, "tax": line.tax_minor, "line_total": line.quantity * line.unit_price_minor + line.tax_minor})
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="invoice.create", entity_type="invoice", entity_id=invoice["id"], outcome="success", request_id=UUID(request.state.request_id), metadata={"total_minor": total, "currency": currency})
    db.commit()
    return {"data": dict(invoice), "meta": {"request_id": request.state.request_id}}


@billing_router.post("/{invoice_id}/payments", status_code=status.HTTP_201_CREATED)
def payment_create(invoice_id: UUID, payload: PaymentCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "billing.manage", csrf_token)
    invoice = db.execute(text("SELECT id, currency, total_minor FROM invoices WHERE clinic_id = :clinic_id AND id = :invoice_id AND status <> 'void' FOR UPDATE"), {"clinic_id": session["clinic_id"], "invoice_id": invoice_id}).mappings().one_or_none()
    if invoice is None:
        raise _error("NOT_FOUND", "Invoice not found.", status.HTTP_404_NOT_FOUND)
    paid = db.execute(text("SELECT COALESCE(sum(amount_minor), 0) FROM payment_allocations WHERE clinic_id = :clinic_id AND invoice_id = :invoice_id"), {"clinic_id": session["clinic_id"], "invoice_id": invoice_id}).scalar_one()
    remaining = invoice["total_minor"] - paid
    if payload.amount_minor > remaining:
        raise _error("INVALID_INPUT", "Payment exceeds the outstanding invoice balance.", status.HTTP_400_BAD_REQUEST)
    payment = db.execute(text("""
        INSERT INTO payments (clinic_id, invoice_id, amount_minor, currency, method, reference, recorded_by_user_id)
        VALUES (:clinic_id, :invoice_id, :amount, :currency, :method, :reference, :user_id)
        RETURNING id, invoice_id, amount_minor, currency, method, reference, paid_at
    """), {"clinic_id": session["clinic_id"], "invoice_id": invoice_id, "amount": payload.amount_minor, "currency": invoice["currency"], "method": payload.method, "reference": payload.reference, "user_id": session["user_id"]}).mappings().one()
    db.execute(text("INSERT INTO payment_allocations (clinic_id, payment_id, invoice_id, amount_minor) VALUES (:clinic_id, :payment_id, :invoice_id, :amount)"), {"clinic_id": session["clinic_id"], "payment_id": payment["id"], "invoice_id": invoice_id, "amount": payload.amount_minor})
    new_paid = paid + payload.amount_minor
    new_status = 'paid' if new_paid == invoice["total_minor"] else 'partially_paid'
    db.execute(text("UPDATE invoices SET status = :status, updated_at = now(), version = version + 1 WHERE clinic_id = :clinic_id AND id = :invoice_id"), {"clinic_id": session["clinic_id"], "invoice_id": invoice_id, "status": new_status})
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="payment.record", entity_type="payment", entity_id=payment["id"], outcome="success", request_id=UUID(request.state.request_id), metadata={"invoice_id": str(invoice_id), "amount_minor": payload.amount_minor, "method": payload.method})
    db.commit()
    return {"data": {**dict(payment), "invoice_status": new_status, "remaining_minor": invoice["total_minor"] - new_paid}, "meta": {"request_id": request.state.request_id}}


@billing_router.get("/{invoice_id}/receipt")
def invoice_receipt(invoice_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "billing.read")
    invoice = db.execute(text("""
        SELECT i.id, i.invoice_number, i.currency, i.subtotal_minor, i.discount_minor, i.tax_minor,
               i.total_minor, i.status, i.issued_at, i.notes, c.name AS clinic_name,
               p.id AS patient_id, p.patient_number, p.full_name AS patient_name
        FROM invoices i
        JOIN clinics c ON c.id = i.clinic_id
        JOIN patients p ON p.clinic_id = i.clinic_id AND p.id = i.patient_id
        WHERE i.clinic_id = :clinic_id AND i.id = :invoice_id
    """), {"clinic_id": session["clinic_id"], "invoice_id": invoice_id}).mappings().one_or_none()
    if invoice is None:
        raise _error("NOT_FOUND", "Invoice not found.", status.HTTP_404_NOT_FOUND)
    lines = db.execute(text("""
        SELECT id, service_id, description, quantity, unit_price_minor, tax_minor, line_total_minor
        FROM invoice_lines WHERE clinic_id = :clinic_id AND invoice_id = :invoice_id ORDER BY id
    """), {"clinic_id": session["clinic_id"], "invoice_id": invoice_id}).mappings().all()
    payments = db.execute(text("""
        SELECT id, amount_minor, currency, method, reference, paid_at
        FROM payments WHERE clinic_id = :clinic_id AND invoice_id = :invoice_id ORDER BY paid_at, id
    """), {"clinic_id": session["clinic_id"], "invoice_id": invoice_id}).mappings().all()
    paid_minor = sum(payment["amount_minor"] for payment in payments)
    db.commit()
    return {"data": {"clinic": {"name": invoice["clinic_name"]}, "patient": {"id": invoice["patient_id"], "patient_number": invoice["patient_number"], "name": invoice["patient_name"]}, "invoice": {**{key: invoice[key] for key in ("id", "invoice_number", "currency", "subtotal_minor", "discount_minor", "tax_minor", "total_minor", "status", "issued_at", "notes")}, "paid_minor": paid_minor, "balance_minor": invoice["total_minor"] - paid_minor}, "lines": [dict(line) for line in lines], "payments": [dict(payment) for payment in payments]}, "meta": {"request_id": request.state.request_id}}

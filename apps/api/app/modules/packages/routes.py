from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.tenant import set_tenant_context
from app.modules.audit.service import record_event
from app.modules.authorization.service import ForbiddenError, require_permission
from app.modules.identity.routes import _error, _session_or_401, _validate_origin
from app.modules.identity.service import SessionError, verify_csrf
from app.modules.packages.schemas import PackageConsume, PackageCreate, PackagePurchase, PackageServiceCreate, PackageStatusUpdate, PackageUpdate

router = APIRouter(prefix="/api/v1/packages", tags=["packages"])


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
def package_list(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "package.read")
    rows = db.execute(text("""
        SELECT p.id, p.name, p.description, p.specialty_id, p.total_price_minor, p.original_value_minor,
               p.currency, p.validity_days, p.status, p.version, p.created_at,
               COALESCE(SUM(ps.sessions_count), 0) AS total_sessions
        FROM package_definitions p
        LEFT JOIN package_services ps ON ps.clinic_id = p.clinic_id AND ps.package_definition_id = p.id
        WHERE p.clinic_id = :clinic_id AND p.archived_at IS NULL
        GROUP BY p.id ORDER BY p.name, p.id
    """), {"clinic_id": session["clinic_id"]}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.get("/overview")
def package_overview(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "package.read")
    row = db.execute(text("""
        SELECT
            (SELECT COUNT(*) FROM package_definitions WHERE clinic_id = :c AND status = 'active' AND archived_at IS NULL) AS active_definitions,
            (SELECT COUNT(*) FROM package_definitions WHERE clinic_id = :c AND status = 'inactive' AND archived_at IS NULL) AS inactive_definitions,
            (SELECT COUNT(*) FROM patient_packages WHERE clinic_id = :c) AS total_sold,
            (SELECT COUNT(*) FROM patient_packages WHERE clinic_id = :c AND status = 'active' AND expires_at > now()) AS active_patient_packages,
            (SELECT COALESCE(SUM(total_sessions), 0) FROM patient_packages WHERE clinic_id = :c) AS sessions_purchased,
            (SELECT COALESCE(SUM(used_sessions), 0) FROM patient_packages WHERE clinic_id = :c) AS sessions_used,
            (SELECT COUNT(*) FROM patient_packages WHERE clinic_id = :c AND status = 'active' AND expires_at BETWEEN now() AND now() + INTERVAL '30 days') AS expiring_30d
    """), {"c": session["clinic_id"]}).mappings().one()
    data = dict(row)
    data["sessions_remaining"] = max(data["sessions_purchased"] - data["sessions_used"], 0)
    db.commit()
    return {"data": data, "meta": {"request_id": request.state.request_id}}


@router.post("", status_code=status.HTTP_201_CREATED)
def package_create(payload: PackageCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "package.manage", csrf_token)
    values = payload.model_dump(exclude={"services"})
    row = db.execute(text("""
        INSERT INTO package_definitions (clinic_id, specialty_id, name, description, total_price_minor, original_value_minor, currency, validity_days)
        VALUES (:clinic_id, :specialty_id, :name, :description, :total_price_minor, :original_value_minor, UPPER(:currency), :validity_days)
        RETURNING id, name, description, specialty_id, total_price_minor, original_value_minor, currency, validity_days, status, version, created_at
    """), {"clinic_id": session["clinic_id"], **values}).mappings().one()
    # Create the included services in the same transaction: a package with no services
    # cannot be sold, so a partially-created shell is exactly the defect being fixed.
    total_sessions = 0
    for item in payload.services:
        added = db.execute(text("""
            INSERT INTO package_services (clinic_id, package_definition_id, service_id, sessions_count)
            SELECT :clinic_id, :package_id, s.id, :sessions_count
            FROM services s WHERE s.clinic_id = :clinic_id AND s.id = :service_id AND s.archived_at IS NULL
            ON CONFLICT (clinic_id, package_definition_id, service_id) DO NOTHING
            RETURNING service_id
        """), {"clinic_id": session["clinic_id"], "package_id": row["id"], "service_id": item.service_id, "sessions_count": item.sessions_count}).scalar_one_or_none()
        if added is None:
            raise _error("INVALID_INPUT", "A selected service is not available in this clinic or is already included once.", status.HTTP_400_BAD_REQUEST, fields={"services": str(item.service_id)})
        total_sessions += item.sessions_count
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="package.create", entity_type="package_definition", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id), metadata={"services": len(payload.services), "total_sessions": total_sessions})
    db.commit()
    data = dict(row)
    data["total_sessions"] = total_sessions
    return {"data": data, "meta": {"request_id": request.state.request_id}}


@router.post("/{package_id}/services", status_code=status.HTTP_201_CREATED)
def package_service_add(package_id: UUID, payload: PackageServiceCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "package.manage", csrf_token)
    already = db.execute(text("SELECT 1 FROM package_services WHERE clinic_id = :c AND package_definition_id = :p AND service_id = :s"), {"c": session["clinic_id"], "p": package_id, "s": payload.service_id}).scalar_one_or_none()
    if already is not None:
        raise _error("INVALID_STATE", "That service is already in this package; remove it first to change the session count.", status.HTTP_409_CONFLICT)
    row = db.execute(text("""
        INSERT INTO package_services (clinic_id, package_definition_id, service_id, sessions_count)
        SELECT :clinic_id, p.id, :service_id, :sessions_count
        FROM package_definitions p JOIN services s ON s.clinic_id = p.clinic_id AND s.id = :service_id AND s.archived_at IS NULL
        WHERE p.clinic_id = :clinic_id AND p.id = :package_id AND p.archived_at IS NULL
        RETURNING package_definition_id, service_id, sessions_count, created_at
    """), {"clinic_id": session["clinic_id"], "package_id": package_id, **payload.model_dump()}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "The package or service is not available in this clinic.", status.HTTP_404_NOT_FOUND)
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.put("/{package_id}")
def package_update(package_id: UUID, payload: PackageUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "package.manage", csrf_token)
    current = db.execute(text("SELECT total_price_minor, original_value_minor FROM package_definitions WHERE clinic_id = :c AND id = :id AND archived_at IS NULL FOR UPDATE"), {"c": session["clinic_id"], "id": package_id}).mappings().one_or_none()
    if current is None:
        raise _error("NOT_FOUND", "Package not found.", status.HTTP_404_NOT_FOUND)
    data = payload.model_dump(exclude_unset=True)
    data.pop("expected_version", None)
    total = data.get("total_price_minor", current["total_price_minor"])
    original = data.get("original_value_minor", current["original_value_minor"])
    if original is not None and original < total:
        raise _error("INVALID_INPUT", "original_value_minor cannot be below total_price_minor.", status.HTTP_400_BAD_REQUEST, fields={"original_value_minor": "must be at least the total price"})
    assignments, params = [], {"c": session["clinic_id"], "id": package_id, "ev": payload.expected_version}
    for key, value in data.items():
        if key == "currency":
            assignments.append("currency = UPPER(:currency)")
        else:
            assignments.append(f"{key} = :{key}")
        params[key] = value
    assignments += ["version = version + 1", "updated_at = now()"]
    updated = db.execute(text(f"""
        UPDATE package_definitions SET {", ".join(assignments)}
        WHERE clinic_id = :c AND id = :id AND version = :ev AND archived_at IS NULL
        RETURNING id, name, description, specialty_id, total_price_minor, original_value_minor, currency, validity_days, status, version, created_at
    """), params).mappings().one_or_none()
    if updated is None:
        existing = db.execute(text("SELECT version, archived_at FROM package_definitions WHERE clinic_id = :c AND id = :id"), {"c": session["clinic_id"], "id": package_id}).mappings().one_or_none()
        if existing is None:
            raise _error("NOT_FOUND", "Package not found.", status.HTTP_404_NOT_FOUND)
        if existing["archived_at"] is not None:
            raise _error("INVALID_STATE", "This package is archived; unarchive it before editing.", status.HTTP_409_CONFLICT)
        raise _error("VERSION_CONFLICT", "The package changed before this edit; reload and retry.", status.HTTP_409_CONFLICT)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="package.update", entity_type="package_definition", entity_id=package_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(updated), "meta": {"request_id": request.state.request_id}}


@router.post("/{package_id}/status")
def package_status(package_id: UUID, payload: PackageStatusUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "package.manage", csrf_token)
    set_clause = {
        "archive": "status = 'archived', archived_at = now()",
        "unarchive": "status = 'active', archived_at = NULL",
        "activate": "status = 'active'",
        "deactivate": "status = 'inactive'",
    }[payload.action]
    # Only valid transitions may run — deactivating an already-inactive package (or
    # archiving twice) must report that state instead of bumping the version silently.
    guard = {
        "archive": "archived_at IS NULL",
        "unarchive": "archived_at IS NOT NULL",
        "activate": "status = 'inactive' AND archived_at IS NULL",
        "deactivate": "status = 'active' AND archived_at IS NULL",
    }[payload.action]
    updated = db.execute(text(f"""
        UPDATE package_definitions SET {set_clause}, version = version + 1, updated_at = now()
        WHERE clinic_id = :c AND id = :id AND version = :ev AND {guard}
        RETURNING id, name, status, version
    """), {"c": session["clinic_id"], "id": package_id, "ev": payload.expected_version}).mappings().one_or_none()
    if updated is None:
        existing = db.execute(text("SELECT status, version, archived_at FROM package_definitions WHERE clinic_id = :c AND id = :id"), {"c": session["clinic_id"], "id": package_id}).mappings().one_or_none()
        if existing is None:
            raise _error("NOT_FOUND", "Package not found.", status.HTTP_404_NOT_FOUND)
        if existing["version"] != payload.expected_version:
            raise _error("VERSION_CONFLICT", "The package changed before this action; reload and retry.", status.HTTP_409_CONFLICT)
        state = "archived" if existing["archived_at"] is not None else existing["status"]
        raise _error("INVALID_STATE", f"This package is already {state}.", status.HTTP_409_CONFLICT)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action=f"package.{payload.action}", entity_type="package_definition", entity_id=package_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(updated), "meta": {"request_id": request.state.request_id}}


@router.delete("/{package_id}/services/{service_id}")
def package_service_remove(package_id: UUID, service_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "package.manage", csrf_token)
    # Safe to remove from the definition: existing patient purchases snapshot their
    # own sessions at purchase time, so historical entitlements are unaffected.
    removed = db.execute(text("DELETE FROM package_services WHERE clinic_id = :c AND package_definition_id = :p AND service_id = :s RETURNING service_id"), {"c": session["clinic_id"], "p": package_id, "s": service_id}).scalar_one_or_none()
    if removed is None:
        raise _error("NOT_FOUND", "The service is not part of this package.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="package.service.remove", entity_type="package_definition", entity_id=package_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": {"removed": True, "service_id": removed}, "meta": {"request_id": request.state.request_id}}


@router.delete("/{package_id}")
def package_delete(package_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    """Hard-delete a package that was never sold. Anything with sales is refused
    (409) so patient_packages/session history can never be cascaded away; archive
    it instead (POST /{id}/status with action=archive) to hide it from the catalog."""
    session = _write_authorized(db, request, session_token, "package.manage", csrf_token)
    definition = db.execute(text("SELECT id FROM package_definitions WHERE clinic_id = :c AND id = :id FOR UPDATE"), {"c": session["clinic_id"], "id": package_id}).scalar_one_or_none()
    if definition is None:
        raise _error("NOT_FOUND", "Package not found.", status.HTTP_404_NOT_FOUND)
    sold = db.execute(text("SELECT COUNT(*) FROM patient_packages WHERE clinic_id = :c AND package_definition_id = :id"), {"c": session["clinic_id"], "id": package_id}).scalar_one()
    if sold > 0:
        # DELETE on patient_packages is RESTRICTed by FK; block explicitly with a helpful message.
        raise _error(
            "PACKAGE_IN_USE",
            f"This package has {sold} sale{'s' if sold != 1 else ''} in patient history and cannot be deleted. Archive it instead — existing purchases keep their sessions.",
            status.HTTP_409_CONFLICT,
            fields={"package_id": "archive instead of delete"},
        )
    db.execute(text("DELETE FROM package_services WHERE clinic_id = :c AND package_definition_id = :id"), {"c": session["clinic_id"], "id": package_id})
    db.execute(text("DELETE FROM package_definitions WHERE clinic_id = :c AND id = :id"), {"c": session["clinic_id"], "id": package_id})
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="package.delete", entity_type="package_definition", entity_id=package_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": {"id": str(package_id), "deleted": True}, "meta": {"request_id": request.state.request_id}}


@router.post("/{package_id}/purchase", status_code=status.HTTP_201_CREATED)
def package_purchase(package_id: UUID, payload: PackagePurchase, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "package.manage", csrf_token)
    # Idempotency: a repeated sell request with the same key returns the original
    # purchase instead of creating a duplicate (the partial unique index is the backstop).
    # Reusing a key for a different patient/package is a conflict, not a replay.
    if payload.idempotency_key is not None:
        existing = db.execute(text("""
            SELECT id, patient_id, package_definition_id, invoice_id, purchased_at, expires_at, status, total_sessions, used_sessions, version
            FROM patient_packages WHERE clinic_id = :clinic_id AND idempotency_key = :key
        """), {"clinic_id": session["clinic_id"], "key": payload.idempotency_key}).mappings().one_or_none()
        if existing is not None:
            if existing["patient_id"] != payload.patient_id or existing["package_definition_id"] != package_id:
                raise _error("IDEMPOTENCY_CONFLICT", "This idempotency key was already used for a different package sale.", status.HTTP_409_CONFLICT)
            db.commit()
            return {"data": dict(existing), "meta": {"request_id": request.state.request_id}}
    # The patient must always belong to this clinic — even when the sale records no invoice.
    patient_ok = db.execute(text("SELECT 1 FROM patients WHERE clinic_id = :clinic_id AND id = :patient_id AND archived_at IS NULL AND duplicate_of IS NULL"), {"clinic_id": session["clinic_id"], "patient_id": payload.patient_id}).scalar_one_or_none()
    if patient_ok is None:
        raise _error("NOT_FOUND", "Patient not found in this clinic.", status.HTTP_404_NOT_FOUND)
    package = db.execute(text("SELECT id, validity_days, total_price_minor, currency, name, status, archived_at FROM package_definitions WHERE clinic_id = :clinic_id AND id = :id FOR UPDATE"), {"clinic_id": session["clinic_id"], "id": package_id}).mappings().one_or_none()
    if package is None:
        raise _error("NOT_FOUND", "Package not found.", status.HTTP_404_NOT_FOUND)
    # Inactive/archived packages must not be sold, and the caller deserves the real reason.
    if package["archived_at"] is not None or package["status"] == "archived":
        raise _error("INVALID_STATE", "This package is archived and can no longer be sold.", status.HTTP_409_CONFLICT)
    if package["status"] != "active":
        raise _error("INVALID_STATE", "This package is inactive and cannot be sold. Reactivate it first.", status.HTTP_409_CONFLICT)
    services = db.execute(text("SELECT service_id, sessions_count FROM package_services WHERE clinic_id = :clinic_id AND package_definition_id = :id ORDER BY service_id"), {"clinic_id": session["clinic_id"], "id": package_id}).mappings().all()
    if not services:
        raise _error("INVALID_STATE", "Add at least one service to the package before purchase.", status.HTTP_400_BAD_REQUEST)
    total_sessions = sum(row["sessions_count"] for row in services)

    # Billing orchestration — atomic within this one transaction. Link an existing invoice,
    # or create a package invoice, and optionally record a payment through the same flow the
    # Billing module uses (invoice-number sequence, payment_allocations, status). An unpaid
    # invoice stays 'unpaid' and is never reported as collected. Mirrors
    # blueprint_core.invoice_create / payment_create to avoid refactoring the billing routes.
    if payload.create_invoice or payload.payment is not None:
        try:
            require_permission(db, session["user_id"], session["clinic_id"], "billing.manage")
        except ForbiddenError as exc:
            raise _error("FORBIDDEN", "Creating an invoice or recording a payment needs the billing.manage permission.", status.HTTP_403_FORBIDDEN) from exc
    resolved_invoice_id = payload.invoice_id
    if payload.invoice_id is not None:
        invoice_ok = db.execute(text("SELECT 1 FROM invoices WHERE clinic_id = :clinic_id AND id = :invoice_id AND patient_id = :patient_id AND status <> 'void'"), {"clinic_id": session["clinic_id"], "invoice_id": payload.invoice_id, "patient_id": payload.patient_id}).scalar_one_or_none()
        if invoice_ok is None:
            raise _error("NOT_FOUND", "The invoice is not associated with this patient.", status.HTTP_404_NOT_FOUND)
    if payload.create_invoice:
        total_minor = package["total_price_minor"]
        year = datetime.now(timezone.utc).year
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(CAST(:k AS text), 0))"), {"k": f"invoice-sequence:{session['clinic_id']}:{year}"})
        sequence = db.execute(text("""
            INSERT INTO invoice_number_sequences (clinic_id, sequence_year, next_value)
            VALUES (:clinic_id, :year, 2)
            ON CONFLICT (clinic_id, sequence_year) DO UPDATE SET next_value = invoice_number_sequences.next_value + 1
            RETURNING next_value - 1 AS sequence_value
        """), {"clinic_id": session["clinic_id"], "year": year}).scalar_one()
        invoice_number = f"CLINIC-{year}-{sequence:06d}"
        invoice_row = db.execute(text("""
            INSERT INTO invoices (clinic_id, patient_id, invoice_number, currency, subtotal_minor, discount_minor, tax_minor, total_minor, created_by_user_id)
            VALUES (:clinic_id, :patient_id, :invoice_number, :currency, :total, 0, 0, :total, :user_id)
            RETURNING id
        """), {"clinic_id": session["clinic_id"], "patient_id": payload.patient_id, "invoice_number": invoice_number, "currency": package["currency"], "total": total_minor, "user_id": session["user_id"]}).mappings().one()
        resolved_invoice_id = invoice_row["id"]
        db.execute(text("""
            INSERT INTO invoice_lines (clinic_id, invoice_id, description, quantity, unit_price_minor, tax_minor, line_total_minor)
            VALUES (:clinic_id, :invoice_id, :description, 1, :total, 0, :total)
        """), {"clinic_id": session["clinic_id"], "invoice_id": resolved_invoice_id, "description": f"Package: {package['name']}", "total": total_minor})
        record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="invoice.create", entity_type="invoice", entity_id=resolved_invoice_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"total_minor": total_minor, "source": "package_sale"})
    invoice_status = None
    if payload.payment is not None:
        invoice = db.execute(text("SELECT id, currency, total_minor FROM invoices WHERE clinic_id = :clinic_id AND id = :invoice_id AND status <> 'void' FOR UPDATE"), {"clinic_id": session["clinic_id"], "invoice_id": resolved_invoice_id}).mappings().one_or_none()
        if invoice is None:
            raise _error("NOT_FOUND", "Invoice not found for the payment.", status.HTTP_404_NOT_FOUND)
        paid = db.execute(text("SELECT COALESCE(SUM(amount_minor), 0) FROM payment_allocations WHERE clinic_id = :clinic_id AND invoice_id = :invoice_id"), {"clinic_id": session["clinic_id"], "invoice_id": resolved_invoice_id}).scalar_one()
        if payload.payment.amount_minor > invoice["total_minor"] - paid:
            raise _error("INVALID_INPUT", "Payment exceeds the outstanding invoice balance.", status.HTTP_400_BAD_REQUEST)
        pay = db.execute(text("""
            INSERT INTO payments (clinic_id, invoice_id, amount_minor, currency, method, reference, recorded_by_user_id)
            VALUES (:clinic_id, :invoice_id, :amount, :currency, :method, :reference, :user_id) RETURNING id
        """), {"clinic_id": session["clinic_id"], "invoice_id": resolved_invoice_id, "amount": payload.payment.amount_minor, "currency": invoice["currency"], "method": payload.payment.method, "reference": payload.payment.reference, "user_id": session["user_id"]}).mappings().one()
        db.execute(text("INSERT INTO payment_allocations (clinic_id, payment_id, invoice_id, amount_minor) VALUES (:clinic_id, :payment_id, :invoice_id, :amount)"), {"clinic_id": session["clinic_id"], "payment_id": pay["id"], "invoice_id": resolved_invoice_id, "amount": payload.payment.amount_minor})
        invoice_status = "paid" if paid + payload.payment.amount_minor == invoice["total_minor"] else "partially_paid"
        db.execute(text("UPDATE invoices SET status = :status, updated_at = now(), version = version + 1 WHERE clinic_id = :clinic_id AND id = :invoice_id"), {"clinic_id": session["clinic_id"], "invoice_id": resolved_invoice_id, "status": invoice_status})
        record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="payment.record", entity_type="payment", entity_id=pay["id"], outcome="success", request_id=UUID(request.state.request_id), metadata={"invoice_id": str(resolved_invoice_id), "amount_minor": payload.payment.amount_minor, "method": payload.payment.method})

    purchased = db.execute(text("""
        INSERT INTO patient_packages (clinic_id, patient_id, package_definition_id, invoice_id, expires_at, total_sessions, idempotency_key)
        VALUES (:clinic_id, :patient_id, :package_id, :invoice_id, now() + (:validity_days * INTERVAL '1 day'), :total_sessions, :idempotency_key)
        RETURNING id, patient_id, package_definition_id, invoice_id, purchased_at, expires_at, status, total_sessions, used_sessions, version
    """), {"clinic_id": session["clinic_id"], "patient_id": payload.patient_id, "package_id": package_id, "invoice_id": resolved_invoice_id, "validity_days": package["validity_days"], "total_sessions": total_sessions, "idempotency_key": payload.idempotency_key}).mappings().one()
    for item in services:
        db.execute(text("""
            INSERT INTO package_sessions (clinic_id, patient_package_id, service_id)
            SELECT :clinic_id, :patient_package_id, :service_id FROM generate_series(1, :sessions_count)
        """), {"clinic_id": session["clinic_id"], "patient_package_id": purchased["id"], "service_id": item["service_id"], "sessions_count": item["sessions_count"]})
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="package.purchase", entity_type="patient_package", entity_id=purchased["id"], outcome="success", request_id=UUID(request.state.request_id), metadata={"patient_id": str(payload.patient_id), "total_sessions": total_sessions})
    db.commit()
    result = dict(purchased)
    if invoice_status is not None:
        result["invoice_status"] = invoice_status
    return {"data": result, "meta": {"request_id": request.state.request_id}}


@router.get("/patients/{patient_id}")
def patient_package_list(patient_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "package.read")
    rows = db.execute(text("""
        SELECT pp.id, pp.patient_id, pp.package_definition_id, p.name, pp.purchased_at, pp.expires_at,
               CASE WHEN pp.status = 'active' AND pp.expires_at <= now() THEN 'expired' ELSE pp.status END AS status,
               pp.total_sessions, pp.used_sessions, GREATEST(pp.total_sessions - pp.used_sessions, 0) AS remaining_sessions, pp.version
        FROM patient_packages pp JOIN package_definitions p ON p.clinic_id = pp.clinic_id AND p.id = pp.package_definition_id
        WHERE pp.clinic_id = :clinic_id AND pp.patient_id = :patient_id ORDER BY pp.purchased_at DESC, pp.id DESC
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.get("/patient-purchases/{patient_package_id}")
def patient_purchase_detail(patient_package_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "package.read")
    purchase = db.execute(text("""
        SELECT pp.id, pp.patient_id, pp.package_definition_id, p.name, pp.invoice_id, pp.purchased_at, pp.expires_at,
               CASE WHEN pp.status = 'active' AND pp.expires_at <= now() THEN 'expired' ELSE pp.status END AS status,
               pp.total_sessions, pp.used_sessions, GREATEST(pp.total_sessions - pp.used_sessions, 0) AS remaining_sessions, pp.version
        FROM patient_packages pp JOIN package_definitions p ON p.clinic_id = pp.clinic_id AND p.id = pp.package_definition_id
        WHERE pp.clinic_id = :c AND pp.id = :id
    """), {"c": session["clinic_id"], "id": patient_package_id}).mappings().one_or_none()
    if purchase is None:
        raise _error("NOT_FOUND", "Patient package not found.", status.HTTP_404_NOT_FOUND)
    sessions = db.execute(text("""
        SELECT psn.id, psn.service_id, s.name AS service_name, psn.appointment_id, psn.status,
               psn.override_reason, psn.used_at, psn.used_by_user_id, psn.created_at
        FROM package_sessions psn LEFT JOIN services s ON s.clinic_id = psn.clinic_id AND s.id = psn.service_id
        WHERE psn.clinic_id = :c AND psn.patient_package_id = :id ORDER BY psn.created_at, psn.id
    """), {"c": session["clinic_id"], "id": patient_package_id}).mappings().all()
    data = dict(purchase)
    data["sessions"] = [dict(row) for row in sessions]
    db.commit()
    return {"data": data, "meta": {"request_id": request.state.request_id}}


@router.get("/{package_id}")
def package_detail(package_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "package.read")
    definition = db.execute(text("""
        SELECT id, name, description, specialty_id, total_price_minor, original_value_minor, currency,
               validity_days, status, version, created_at, updated_at
        FROM package_definitions WHERE clinic_id = :c AND id = :id
    """), {"c": session["clinic_id"], "id": package_id}).mappings().one_or_none()
    if definition is None:
        raise _error("NOT_FOUND", "Package not found.", status.HTTP_404_NOT_FOUND)
    services = db.execute(text("""
        SELECT ps.service_id, s.name, ps.sessions_count
        FROM package_services ps JOIN services s ON s.clinic_id = ps.clinic_id AND s.id = ps.service_id
        WHERE ps.clinic_id = :c AND ps.package_definition_id = :id ORDER BY s.name, ps.service_id
    """), {"c": session["clinic_id"], "id": package_id}).mappings().all()
    sold = db.execute(text("""
        SELECT COUNT(*) AS total_sold,
               COUNT(*) FILTER (WHERE status = 'active' AND expires_at > now()) AS active_count
        FROM patient_packages WHERE clinic_id = :c AND package_definition_id = :id
    """), {"c": session["clinic_id"], "id": package_id}).mappings().one()
    data = dict(definition)
    data["services"] = [dict(row) for row in services]
    data["total_sessions"] = sum(row["sessions_count"] for row in services)
    data["sold"] = dict(sold)
    db.commit()
    return {"data": data, "meta": {"request_id": request.state.request_id}}


@router.post("/patient-purchases/{patient_package_id}/consume", status_code=status.HTTP_201_CREATED)
def package_consume(patient_package_id: UUID, payload: PackageConsume, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "package.manage", csrf_token)
    package = db.execute(text("""
        SELECT pp.id, pp.patient_id, pp.status, pp.expires_at, pp.total_sessions, pp.used_sessions
        FROM patient_packages pp WHERE pp.clinic_id = :clinic_id AND pp.id = :id FOR UPDATE
    """), {"clinic_id": session["clinic_id"], "id": patient_package_id}).mappings().one_or_none()
    if package is None:
        raise _error("NOT_FOUND", "Patient package not found.", status.HTTP_404_NOT_FOUND)
    if package["expires_at"] <= datetime.now(timezone.utc) or package["status"] in ("expired", "cancelled"):
        raise _error("INVALID_STATE", "This package has expired or is cancelled.", status.HTTP_409_CONFLICT)
    query = "SELECT id, service_id FROM package_sessions WHERE clinic_id = :clinic_id AND patient_package_id = :package_id AND status = 'planned'"
    params = {"clinic_id": session["clinic_id"], "package_id": patient_package_id}
    if payload.service_id is not None:
        query += " AND service_id = :service_id"; params["service_id"] = payload.service_id
    session_row = db.execute(text(query + " ORDER BY created_at, id LIMIT 1 FOR UPDATE"), params).mappings().one_or_none()
    override = False
    if session_row is None:
        if not payload.override_reason:
            raise _error("PACKAGE_EXHAUSTED", "No remaining package session matches this service.", status.HTTP_409_CONFLICT)
        try:
            require_permission(db, session["user_id"], session["clinic_id"], "package.override")
        except ForbiddenError as exc:
            raise _error("FORBIDDEN", "An authorized package override is required.", status.HTTP_403_FORBIDDEN) from exc
        override = True
    if payload.appointment_id is not None:
        appointment_ok = db.execute(text("SELECT 1 FROM appointments WHERE clinic_id = :clinic_id AND id = :appointment_id AND patient_id = :patient_id AND archived_at IS NULL"), {"clinic_id": session["clinic_id"], "appointment_id": payload.appointment_id, "patient_id": package["patient_id"]}).scalar_one_or_none()
        if appointment_ok is None:
            raise _error("NOT_FOUND", "The appointment is not associated with this patient.", status.HTTP_404_NOT_FOUND)
    if override:
        row = db.execute(text("""
            INSERT INTO package_sessions (clinic_id, patient_package_id, service_id, appointment_id, status, override_reason, used_at, used_by_user_id)
            VALUES (:clinic_id, :package_id, :service_id, :appointment_id, 'overuse_override', :reason, now(), :user_id)
            RETURNING id, service_id, appointment_id, status, override_reason, used_at
        """), {"clinic_id": session["clinic_id"], "package_id": patient_package_id, "service_id": payload.service_id, "appointment_id": payload.appointment_id, "reason": payload.override_reason, "user_id": session["user_id"]}).mappings().one()
    else:
        row = db.execute(text("UPDATE package_sessions SET status = 'used', appointment_id = :appointment_id, used_at = now(), used_by_user_id = :user_id WHERE clinic_id = :clinic_id AND id = :id RETURNING id, service_id, appointment_id, status, override_reason, used_at"), {"clinic_id": session["clinic_id"], "id": session_row["id"], "appointment_id": payload.appointment_id, "user_id": session["user_id"]}).mappings().one()
    # ck_patient_packages_used caps used_sessions at total_sessions; an authorised override is
    # still recorded in the session ledger, but the counter must not violate that check.
    db.execute(text("UPDATE patient_packages SET used_sessions = CASE WHEN :override THEN LEAST(used_sessions + 1, total_sessions) ELSE used_sessions + 1 END, status = CASE WHEN used_sessions + 1 >= total_sessions AND :override = false THEN 'exhausted' ELSE status END, version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :id"), {"clinic_id": session["clinic_id"], "id": patient_package_id, "override": override})
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="package.session.consume", entity_type="package_session", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id), metadata={"patient_package_id": str(patient_package_id), "override": override})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}

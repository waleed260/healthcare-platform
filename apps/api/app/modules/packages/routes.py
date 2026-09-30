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
from app.modules.packages.schemas import PackageConsume, PackageCreate, PackagePurchase, PackageServiceCreate

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
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.post("", status_code=status.HTTP_201_CREATED)
def package_create(payload: PackageCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "package.manage", csrf_token)
    row = db.execute(text("""
        INSERT INTO package_definitions (clinic_id, specialty_id, name, description, total_price_minor, original_value_minor, currency, validity_days)
        VALUES (:clinic_id, :specialty_id, :name, :description, :total_price_minor, :original_value_minor, UPPER(:currency), :validity_days)
        RETURNING id, name, description, specialty_id, total_price_minor, original_value_minor, currency, validity_days, status, version, created_at
    """), {"clinic_id": session["clinic_id"], **payload.model_dump()}).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="package.create", entity_type="package_definition", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.post("/{package_id}/services", status_code=status.HTTP_201_CREATED)
def package_service_add(package_id: UUID, payload: PackageServiceCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "package.manage", csrf_token)
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


@router.post("/{package_id}/purchase", status_code=status.HTTP_201_CREATED)
def package_purchase(package_id: UUID, payload: PackagePurchase, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "package.manage", csrf_token)
    package = db.execute(text("SELECT id, validity_days FROM package_definitions WHERE clinic_id = :clinic_id AND id = :id AND status = 'active' AND archived_at IS NULL FOR UPDATE"), {"clinic_id": session["clinic_id"], "id": package_id}).mappings().one_or_none()
    if package is None:
        raise _error("NOT_FOUND", "Package not found.", status.HTTP_404_NOT_FOUND)
    services = db.execute(text("SELECT service_id, sessions_count FROM package_services WHERE clinic_id = :clinic_id AND package_definition_id = :id ORDER BY service_id"), {"clinic_id": session["clinic_id"], "id": package_id}).mappings().all()
    if not services:
        raise _error("INVALID_STATE", "Add at least one service to the package before purchase.", status.HTTP_400_BAD_REQUEST)
    total_sessions = sum(row["sessions_count"] for row in services)
    purchased = db.execute(text("""
        INSERT INTO patient_packages (clinic_id, patient_id, package_definition_id, invoice_id, expires_at, total_sessions)
        VALUES (:clinic_id, :patient_id, :package_id, :invoice_id, now() + (:validity_days * INTERVAL '1 day'), :total_sessions)
        RETURNING id, patient_id, package_definition_id, invoice_id, purchased_at, expires_at, status, total_sessions, used_sessions, version
    """), {"clinic_id": session["clinic_id"], "patient_id": payload.patient_id, "package_id": package_id, "invoice_id": payload.invoice_id, "validity_days": package["validity_days"], "total_sessions": total_sessions}).mappings().one()
    for item in services:
        db.execute(text("""
            INSERT INTO package_sessions (clinic_id, patient_package_id, service_id)
            SELECT :clinic_id, :patient_package_id, :service_id FROM generate_series(1, :sessions_count)
        """), {"clinic_id": session["clinic_id"], "patient_package_id": purchased["id"], "service_id": item["service_id"], "sessions_count": item["sessions_count"]})
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="package.purchase", entity_type="patient_package", entity_id=purchased["id"], outcome="success", request_id=UUID(request.state.request_id), metadata={"patient_id": str(payload.patient_id), "total_sessions": total_sessions})
    db.commit()
    return {"data": dict(purchased), "meta": {"request_id": request.state.request_id}}


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
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


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
    db.execute(text("UPDATE patient_packages SET used_sessions = used_sessions + 1, status = CASE WHEN used_sessions + 1 >= total_sessions AND :override = false THEN 'exhausted' ELSE status END, version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :id"), {"clinic_id": session["clinic_id"], "id": patient_package_id, "override": override})
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="package.session.consume", entity_type="package_session", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id), metadata={"patient_package_id": str(patient_package_id), "override": override})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}

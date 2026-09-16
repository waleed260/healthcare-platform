from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import secrets
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Cookie, Header, Query, Request, Response, status
from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import decode_cursor, encode_cursor, hash_token
from app.db.session import get_db
from app.db.tenant import set_tenant_context
from app.modules.identity.routes import _error
from app.modules.appointments.schemas import PublicBookingRequest
from app.modules.appointments.schemas import AppointmentAssignRequest, AppointmentDecisionRequest, AppointmentRescheduleRequest, AppointmentTransitionRequest, PublicCancelRequest, PublicRescheduleRequest
from app.modules.appointments.availability import AvailabilityInterval, generate_slots
from app.modules.appointments.state import validate_transition
from app.modules.authorization.service import ForbiddenError, require_permission
from app.modules.identity.routes import _session_or_401, _validate_origin
from app.modules.identity.service import SessionError, verify_csrf
from app.modules.audit.service import record_event
from app.modules.appointments.rate_limit import consume_public_management_limit

router = APIRouter(prefix="/api/v1/public/bookings", tags=["public-bookings"])
availability_router = APIRouter(prefix="/api/v1/public/availability", tags=["public-availability"])
catalog_router = APIRouter(prefix="/api/v1/public/catalog", tags=["public-catalog"])
appointment_router = APIRouter(prefix="/api/v1/appointments", tags=["appointments"])
management_router = APIRouter(prefix="/api/v1/public/booking-management", tags=["public-booking-management"])
question_router = APIRouter(prefix="/api/v1/public/booking-questions", tags=["public-booking-questions"])


@catalog_router.get("")
def public_catalog(*, request: Request, clinic_slug: str = Query(min_length=1, max_length=120), db: Session = Depends(get_db)) -> dict:
    clinic_id = db.execute(text("SELECT id, name, timezone, locale FROM clinics WHERE slug = :slug AND archived_at IS NULL AND status = 'active'"), {"slug": clinic_slug.strip().casefold()}).mappings().one_or_none()
    if clinic_id is None:
        raise _error("NOT_FOUND", "Clinic not found.", status.HTTP_404_NOT_FOUND)
    set_tenant_context(db, clinic_id["id"])
    branches = db.execute(text("""
        SELECT id, code, name, timezone, address, phone
        FROM branches
        WHERE clinic_id = :clinic_id AND status = 'active' AND archived_at IS NULL
        ORDER BY name, id
    """), {"clinic_id": clinic_id["id"]}).mappings().all()
    services = db.execute(text("""
        SELECT s.id, s.name, s.category, s.short_description, s.duration_minutes,
               s.amount_minor, s.currency, bs.branch_id
        FROM services s
        JOIN branch_services bs ON bs.clinic_id = s.clinic_id AND bs.service_id = s.id
        WHERE s.clinic_id = :clinic_id AND s.status = 'active' AND s.visibility = 'public'
        ORDER BY s.name, s.id, bs.branch_id
    """), {"clinic_id": clinic_id["id"]}).mappings().all()
    doctors = db.execute(text("""
        SELECT d.id, d.public_name, d.specialty, bd.branch_id, ds.service_id
        FROM doctor_profiles d
        JOIN branch_doctors bd ON bd.clinic_id = d.clinic_id AND bd.doctor_id = d.id
        JOIN doctor_services ds ON ds.clinic_id = d.clinic_id AND ds.doctor_id = d.id
        JOIN branch_services bs ON bs.clinic_id = d.clinic_id AND bs.branch_id = bd.branch_id AND bs.service_id = ds.service_id
        WHERE d.clinic_id = :clinic_id AND d.status = 'active' AND d.archived_at IS NULL
        ORDER BY d.public_name, d.id
    """), {"clinic_id": clinic_id["id"]}).mappings().all()
    db.commit()
    return {"data": {"clinic": dict(clinic_id), "branches": [dict(row) for row in branches], "services": [dict(row) for row in services], "doctors": [dict(row) for row in doctors]}, "meta": {"request_id": request.state.request_id}}


def _validate_availability_range(from_date: date, to_date: date) -> None:
    if to_date < from_date or (to_date - from_date).days > 89:
        raise _error("INVALID_INPUT", "Availability range must be between one and 90 days.", status.HTTP_400_BAD_REQUEST)


def _management_context(db: Session, clinic_slug: str | None) -> UUID:
    if not clinic_slug:
        raise _error("INVALID_INPUT", "Clinic resolution is required.", status.HTTP_400_BAD_REQUEST)
    clinic_id = db.execute(text("SELECT id FROM clinics WHERE slug = :slug AND archived_at IS NULL AND status = 'active'"), {"slug": clinic_slug.strip().casefold()}).scalar_one_or_none()
    if clinic_id is None:
        raise _error("NOT_FOUND", "Clinic not found.", status.HTTP_404_NOT_FOUND)
    set_tenant_context(db, clinic_id)
    return clinic_id


def _enforce_management_rate_limit(db: Session, request: Request, clinic_id: UUID, reference: str) -> None:
    ip_address = request.client.host if request.client else "unknown"
    allowed = consume_public_management_limit(db, clinic_id=clinic_id, reference=reference, ip_address=ip_address)
    db.commit()
    set_tenant_context(db, clinic_id)
    if not allowed:
        raise _error("RATE_LIMITED", "Too many booking-management attempts. Try again shortly.", status.HTTP_429_TOO_MANY_REQUESTS)


def _managed_appointment(db: Session, clinic_id: UUID, reference: str, token: str | None, lock: bool = False) -> dict:
    if not token:
        raise _error("NOT_FOUND", "Appointment not found.", status.HTTP_404_NOT_FOUND)
    suffix = " FOR UPDATE" if lock else ""
    row = db.execute(text(f"""
        SELECT a.id, a.reference, a.status, a.starts_at, a.ends_at, a.version, t.expires_at
        FROM appointments a JOIN booking_management_tokens t ON t.clinic_id = a.clinic_id AND t.appointment_id = a.id
        WHERE a.clinic_id = :clinic_id AND a.reference = :reference AND t.secret_hash = :secret_hash
          AND t.revoked_at IS NULL AND t.expires_at > now() AND a.archived_at IS NULL{suffix}
    """), {"clinic_id": clinic_id, "reference": reference.strip(), "secret_hash": hash_token(token)}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Appointment not found.", status.HTTP_404_NOT_FOUND)
    return dict(row)


@management_router.get("/{reference}")
def public_management_summary(reference: str, request: Request, clinic_slug: str | None = Header(default=None, alias="X-Clinic-Slug"), management_token: str | None = Header(default=None, alias="X-Management-Token"), db: Session = Depends(get_db)) -> dict:
    clinic_id = _management_context(db, clinic_slug)
    _enforce_management_rate_limit(db, request, clinic_id, reference)
    appointment = _managed_appointment(db, clinic_id, reference, management_token)
    db.commit()
    return {"data": {"reference": appointment["reference"], "status": appointment["status"], "starts_at": appointment["starts_at"], "ends_at": appointment["ends_at"]}, "meta": {"request_id": request.state.request_id}}


@management_router.post("/{reference}/cancel")
def public_management_cancel(reference: str, payload: PublicCancelRequest, request: Request, clinic_slug: str | None = Header(default=None, alias="X-Clinic-Slug"), management_token: str | None = Header(default=None, alias="X-Management-Token"), db: Session = Depends(get_db)) -> dict:
    clinic_id = _management_context(db, clinic_slug)
    _enforce_management_rate_limit(db, request, clinic_id, reference)
    appointment = _managed_appointment(db, clinic_id, reference, management_token, lock=True)
    try:
        validate_transition(appointment["status"], "cancelled")
    except ValueError as exc:
        raise _error("INVALID_TRANSITION", "This appointment cannot be cancelled.", status.HTTP_400_BAD_REQUEST) from exc
    db.execute(text("UPDATE appointments SET status = 'cancelled', blocks_time = false, cancellation_reason = :reason, status_changed_at = now(), version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :id"), {"clinic_id": clinic_id, "id": appointment["id"], "reason": payload.reason})
    db.execute(text("INSERT INTO appointment_history (clinic_id, appointment_id, from_status, to_status, reason) VALUES (:clinic_id, :id, :from_status, 'cancelled', :reason)"), {"clinic_id": clinic_id, "id": appointment["id"], "from_status": appointment["status"], "reason": payload.reason})
    db.execute(text("UPDATE booking_management_tokens SET revoked_at = now() WHERE clinic_id = :clinic_id AND appointment_id = :id"), {"clinic_id": clinic_id, "id": appointment["id"]})
    record_event(db, clinic_id=clinic_id, actor_user_id=None, action="public_appointment.cancel", entity_type="appointment", entity_id=appointment["id"], outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": {"reference": appointment["reference"], "status": "cancelled"}, "meta": {"request_id": request.state.request_id}}


@management_router.post("/{reference}/reschedule-request", status_code=status.HTTP_201_CREATED)
def public_management_reschedule(reference: str, payload: PublicRescheduleRequest, request: Request, clinic_slug: str | None = Header(default=None, alias="X-Clinic-Slug"), management_token: str | None = Header(default=None, alias="X-Management-Token"), db: Session = Depends(get_db)) -> dict:
    clinic_id = _management_context(db, clinic_slug)
    _enforce_management_rate_limit(db, request, clinic_id, reference)
    appointment = _managed_appointment(db, clinic_id, reference, management_token, lock=True)
    if appointment["status"] not in {"requested", "confirmed"}:
        raise _error("INVALID_TRANSITION", "This appointment cannot be rescheduled.", status.HTTP_400_BAD_REQUEST)
    if payload.starts_at.tzinfo is None:
        raise _error("INVALID_INPUT", "starts_at must include a timezone offset.", status.HTTP_400_BAD_REQUEST)
    request_row = db.execute(text("INSERT INTO appointment_reschedule_requests (clinic_id, appointment_id, requested_starts_at, reason) VALUES (:clinic_id, :id, :starts_at, :reason) RETURNING id, status, created_at"), {"clinic_id": clinic_id, "id": appointment["id"], "starts_at": payload.starts_at, "reason": payload.reason}).mappings().one()
    record_event(db, clinic_id=clinic_id, actor_user_id=None, action="public_appointment.reschedule_request", entity_type="appointment", entity_id=appointment["id"], outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": {"reference": appointment["reference"], "request": dict(request_row)}, "meta": {"request_id": request.state.request_id}}


def _staff_authorized(db: Session, session_token: str | None, permission: str, branch_id: UUID | None = None) -> dict:
    session = _session_or_401(db, session_token)
    if session["clinic_id"] is None:
        raise _error("FORBIDDEN", "A clinic context is required.", status.HTTP_403_FORBIDDEN)
    set_tenant_context(db, session["clinic_id"], session["user_id"])
    try:
        require_permission(db, session["user_id"], session["clinic_id"], permission, branch_id=branch_id)
    except ForbiddenError as exc:
        raise _error("FORBIDDEN", "You do not have permission for this appointment command.", status.HTTP_403_FORBIDDEN) from exc
    return session


def _appointment_branch_id(db: Session, session_token: str | None, appointment_id: UUID) -> UUID:
    """Resolve the appointment's branch under the caller's tenant context."""
    session = _session_or_401(db, session_token)
    if session["clinic_id"] is None:
        raise _error("FORBIDDEN", "A clinic context is required.", status.HTTP_403_FORBIDDEN)
    set_tenant_context(db, session["clinic_id"], session["user_id"])
    branch_id = db.execute(text("SELECT branch_id FROM appointments WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL"), {"clinic_id": session["clinic_id"], "id": appointment_id}).scalar_one_or_none()
    if branch_id is None:
        raise _error("NOT_FOUND", "Appointment not found.", status.HTTP_404_NOT_FOUND)
    return branch_id


def _csrf(request: Request, session: dict, csrf_token: str | None) -> None:
    _validate_origin(request)
    if not csrf_token:
        raise _error("CSRF_REQUIRED", "A CSRF token is required.", status.HTTP_403_FORBIDDEN)
    try:
        verify_csrf(session, csrf_token)
    except SessionError as exc:
        raise _error("CSRF_INVALID", "The CSRF token is invalid.", status.HTTP_403_FORBIDDEN) from exc


def _audit(db: Session, request: Request, session: dict, action: str, appointment_id: UUID, outcome: str = "success") -> None:
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action=action, entity_type="appointment", entity_id=appointment_id, outcome=outcome, request_id=UUID(request.state.request_id))


@appointment_router.get("")
def appointment_list(request: Request, branch_id: UUID | None = Query(default=None), appointment_status: str | None = Query(default=None, alias="status", max_length=40), cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _staff_authorized(db, session_token, "appointment.read", branch_id=branch_id)
    cursor_values = decode_cursor(cursor, "appointments") if cursor else None
    if cursor and (cursor_values is None or cursor_values.get("branch_id") != str(branch_id) or cursor_values.get("status") != (appointment_status or "")):
        raise _error("INVALID_INPUT", "The page cursor is invalid or does not match these filters.", status.HTTP_400_BAD_REQUEST)
    try:
        after_starts_at = datetime.fromisoformat(cursor_values["starts_at"]) if cursor_values else None
        after_id = UUID(cursor_values["id"]) if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT id, reference, branch_id, doctor_id, service_id, patient_id, starts_at, ends_at, status, source, version, created_at, updated_at
        FROM appointments
        WHERE clinic_id = :clinic_id AND archived_at IS NULL
          AND (:branch_id IS NULL OR branch_id = :branch_id)
          AND (
            NOT EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id)
            OR EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id AND s.branch_id = appointments.branch_id)
          )
          AND (:appointment_status IS NULL OR status = :appointment_status)
          AND (:after_starts_at IS NULL OR starts_at > :after_starts_at OR (starts_at = :after_starts_at AND id > :after_id))
        ORDER BY starts_at, id LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "branch_id": branch_id, "appointment_status": appointment_status, "after_starts_at": after_starts_at, "after_id": after_id, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_next and rows:
        next_cursor = encode_cursor("appointments", {"branch_id": str(branch_id), "status": appointment_status or "", "starts_at": rows[-1]["starts_at"].isoformat(), "id": str(rows[-1]["id"])})
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@appointment_router.get("/{appointment_id}")
def appointment_detail(appointment_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    branch_id = _appointment_branch_id(db, session_token, appointment_id)
    session = _staff_authorized(db, session_token, "appointment.read", branch_id=branch_id)
    row = db.execute(text("SELECT id, reference, branch_id, doctor_id, service_id, patient_id, starts_at, ends_at, occupancy_start, occupancy_end, status, source, policy_snapshot, version, created_at, updated_at FROM appointments WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL"), {"clinic_id": session["clinic_id"], "id": appointment_id}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Appointment not found.", status.HTTP_404_NOT_FOUND)
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@appointment_router.get("/{appointment_id}/history")
def appointment_history(appointment_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    branch_id = _appointment_branch_id(db, session_token, appointment_id)
    session = _staff_authorized(db, session_token, "appointment.read", branch_id=branch_id)
    rows = db.execute(text("SELECT id, from_status, to_status, actor_user_id, reason, created_at FROM appointment_history WHERE clinic_id = :clinic_id AND appointment_id = :id ORDER BY created_at, id"), {"clinic_id": session["clinic_id"], "id": appointment_id}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@appointment_router.post("/{appointment_id}/assign")
def appointment_assign(appointment_id: UUID, payload: AppointmentAssignRequest, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    branch_id = _appointment_branch_id(db, session_token, appointment_id)
    session = _staff_authorized(db, session_token, "appointment.manage", branch_id=branch_id)
    _csrf(request, session, csrf_token)
    if payload.doctor_id is not None and db.execute(text("""
        SELECT 1
        FROM branch_doctors bd
        JOIN doctor_profiles d ON d.clinic_id = bd.clinic_id AND d.id = bd.doctor_id
        WHERE bd.clinic_id = :clinic_id AND bd.branch_id = :branch_id AND bd.doctor_id = :doctor_id
          AND d.status = 'active' AND d.archived_at IS NULL
    """), {"clinic_id": session["clinic_id"], "branch_id": branch_id, "doctor_id": payload.doctor_id}).scalar_one_or_none() is None:
        raise _error("NOT_FOUND", "The doctor is not assigned to this branch.", status.HTTP_404_NOT_FOUND)
    row = db.execute(text("UPDATE appointments SET doctor_id = :doctor_id, version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL AND version = :expected_version RETURNING id, doctor_id, version, updated_at"), {"clinic_id": session["clinic_id"], "id": appointment_id, "doctor_id": payload.doctor_id, "expected_version": payload.expected_version}).mappings().one_or_none()
    if row is None:
        raise _error("VERSION_CONFLICT", "The appointment changed before assignment.", status.HTTP_409_CONFLICT)
    _audit(db, request, session, "appointment.assign", appointment_id)
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@appointment_router.post("/{appointment_id}/transitions")
def appointment_transition(appointment_id: UUID, payload: AppointmentTransitionRequest, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    permission = "appointment.approve" if payload.to_status == "confirmed" else ("appointment.cancel" if payload.to_status == "cancelled" else ("appointment.check_in" if payload.to_status == "arrived" else "appointment.manage"))
    branch_id = _appointment_branch_id(db, session_token, appointment_id)
    session = _staff_authorized(db, session_token, permission, branch_id=branch_id)
    _csrf(request, session, csrf_token)
    row = db.execute(text("SELECT id, status, version FROM appointments WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL FOR UPDATE"), {"clinic_id": session["clinic_id"], "id": appointment_id}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Appointment not found.", status.HTTP_404_NOT_FOUND)
    if row["version"] != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The appointment changed before this command.", status.HTTP_409_CONFLICT)
    if payload.to_status == "cancelled" and not payload.reason_code:
        raise _error("INVALID_INPUT", "Cancellation requires a reason code.", status.HTTP_400_BAD_REQUEST)
    try:
        validate_transition(row["status"], payload.to_status)
    except ValueError as exc:
        raise _error("INVALID_TRANSITION", "This appointment cannot make that transition.", status.HTTP_400_BAD_REQUEST) from exc
    blocks_time = payload.to_status not in {"cancelled", "rescheduled", "no_show"}
    reason = ": ".join(value for value in (payload.reason_code, payload.note) if value)
    updated = db.execute(text("UPDATE appointments SET status = :status, blocks_time = :blocks_time, cancellation_reason = :reason, status_changed_at = now(), version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :id RETURNING id, status, version, status_changed_at"), {"clinic_id": session["clinic_id"], "id": appointment_id, "status": payload.to_status, "blocks_time": blocks_time, "reason": reason or None}).mappings().one()
    db.execute(text("INSERT INTO appointment_history (clinic_id, appointment_id, from_status, to_status, actor_user_id, reason) VALUES (:clinic_id, :id, :from_status, :to_status, :actor, :reason)"), {"clinic_id": session["clinic_id"], "id": appointment_id, "from_status": row["status"], "to_status": payload.to_status, "actor": session["user_id"], "reason": reason or None})
    _audit(db, request, session, f"appointment.{payload.to_status}", appointment_id)
    db.commit()
    return {"data": dict(updated), "meta": {"request_id": request.state.request_id}}


@appointment_router.post("/{appointment_id}/approve")
def appointment_approve(appointment_id: UUID, payload: AppointmentDecisionRequest, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    return appointment_transition(
        appointment_id,
        AppointmentTransitionRequest(to_status="confirmed", **payload.model_dump()),
        request,
        db,
        session_token,
        csrf_token,
    )


@appointment_router.post("/{appointment_id}/reject")
def appointment_reject(appointment_id: UUID, payload: AppointmentDecisionRequest, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    return appointment_transition(
        appointment_id,
        AppointmentTransitionRequest(to_status="cancelled", **payload.model_dump()),
        request,
        db,
        session_token,
        csrf_token,
    )


@appointment_router.post("/{appointment_id}/cancel")
def appointment_cancel(appointment_id: UUID, payload: AppointmentDecisionRequest, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    return appointment_transition(
        appointment_id,
        AppointmentTransitionRequest(to_status="cancelled", **payload.model_dump()),
        request,
        db,
        session_token,
        csrf_token,
    )


@appointment_router.post("/{appointment_id}/reschedule", status_code=status.HTTP_201_CREATED)
def appointment_reschedule(appointment_id: UUID, payload: AppointmentRescheduleRequest, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    branch_id = _appointment_branch_id(db, session_token, appointment_id)
    session = _staff_authorized(db, session_token, "appointment.reschedule", branch_id=branch_id)
    _csrf(request, session, csrf_token)
    old = db.execute(text("SELECT id, branch_id, doctor_id, service_id, patient_id, starts_at, ends_at, occupancy_start, occupancy_end, status, version, policy_snapshot FROM appointments WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL FOR UPDATE"), {"clinic_id": session["clinic_id"], "id": appointment_id}).mappings().one_or_none()
    if old is None:
        raise _error("NOT_FOUND", "Appointment not found.", status.HTTP_404_NOT_FOUND)
    if old["version"] != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The appointment changed before rescheduling.", status.HTTP_409_CONFLICT)
    if old["status"] not in {"confirmed", "requested"}:
        raise _error("INVALID_TRANSITION", "Only requested or confirmed appointments can be rescheduled.", status.HTTP_400_BAD_REQUEST)
    if payload.starts_at.tzinfo is None:
        raise _error("INVALID_INPUT", "starts_at must include a timezone offset.", status.HTTP_400_BAD_REQUEST)
    branch = db.execute(text("SELECT timezone FROM branches WHERE clinic_id = :clinic_id AND id = :branch_id AND status = 'active' AND archived_at IS NULL"), {"clinic_id": session["clinic_id"], "branch_id": old["branch_id"]}).mappings().one_or_none()
    if branch is None:
        raise _error("NOT_FOUND", "The appointment branch is no longer available.", status.HTTP_404_NOT_FOUND)
    policy = old["policy_snapshot"] or {}
    duration = int(policy.get("duration_minutes", round((old["ends_at"] - old["starts_at"]).total_seconds() / 60)))
    before = int(policy.get("buffer_before_minutes", 0))
    after = int(policy.get("buffer_after_minutes", 0))
    starts_at = payload.starts_at.astimezone(timezone.utc)
    ends_at = starts_at + timedelta(minutes=duration)
    occupancy_start = starts_at - timedelta(minutes=before)
    occupancy_end = ends_at + timedelta(minutes=after)
    _validate_commit_time(db=db, clinic_id=session["clinic_id"], branch_id=old["branch_id"], doctor_id=old["doctor_id"], service_id=old["service_id"], branch_timezone=branch["timezone"], starts_at=starts_at, ends_at=ends_at, occupancy_start=occupancy_start, occupancy_end=occupancy_end, exclude_appointment_id=appointment_id)
    # Make the superseded row non-blocking before the replacement insert. Both
    # changes remain in one transaction, so a failed insert rolls this back.
    transitioned = db.execute(text("UPDATE appointments SET status = 'rescheduled', blocks_time = false, status_changed_at = now(), version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :id AND version = :expected_version RETURNING id"), {"clinic_id": session["clinic_id"], "id": appointment_id, "expected_version": payload.expected_version}).scalar_one_or_none()
    if transitioned is None:
        db.rollback()
        raise _error("VERSION_CONFLICT", "The appointment changed before rescheduling.", status.HTTP_409_CONFLICT)
    try:
        replacement = db.execute(text("""
            INSERT INTO appointments (clinic_id, branch_id, doctor_id, service_id, patient_id, starts_at, ends_at, occupancy_start, occupancy_end, status, blocks_time, source, reference, idempotency_key, idempotency_body_hash, policy_snapshot, supersedes_appointment_id, status_changed_at)
            VALUES (:clinic_id, :branch_id, :doctor_id, :service_id, :patient_id, :starts_at, :ends_at, :occupancy_start, :occupancy_end, :status, true, 'staff', :reference, :idempotency_key, :body_hash, CAST(:policy AS jsonb), :supersedes, now())
            RETURNING id, reference, status, version, starts_at, ends_at
        """), {"clinic_id": session["clinic_id"], "branch_id": old["branch_id"], "doctor_id": old["doctor_id"], "service_id": old["service_id"], "patient_id": old["patient_id"], "starts_at": starts_at, "ends_at": ends_at, "occupancy_start": occupancy_start, "occupancy_end": occupancy_end, "status": old["status"], "reference": f"RS-{secrets.token_hex(5).upper()}", "idempotency_key": f"reschedule:{appointment_id}:{payload.expected_version}:{starts_at.isoformat()}", "body_hash": hashlib.sha256(f"{appointment_id}:{starts_at.isoformat()}".encode()).hexdigest(), "policy": json.dumps(policy), "supersedes": appointment_id}).mappings().one()
    except Exception as exc:
        db.rollback()
        if "no_doctor_overlap" in str(exc):
            raise _error("APPOINTMENT_CONFLICT", "The selected time is no longer available.", status.HTTP_409_CONFLICT) from exc
        raise
    management_secret = secrets.token_urlsafe(32)
    db.execute(text("INSERT INTO appointment_history (clinic_id, appointment_id, from_status, to_status, actor_user_id, reason) VALUES (:clinic_id, :old_id, :old_status, 'rescheduled', :actor, :reason), (:clinic_id, :new_id, NULL, :new_status, :actor, :reason)"), {"clinic_id": session["clinic_id"], "old_id": appointment_id, "old_status": old["status"], "new_id": replacement["id"], "new_status": old["status"], "actor": session["user_id"], "reason": payload.reason})
    db.execute(text("UPDATE booking_management_tokens SET revoked_at = now() WHERE clinic_id = :clinic_id AND appointment_id = :old_id AND revoked_at IS NULL"), {"clinic_id": session["clinic_id"], "old_id": appointment_id})
    db.execute(text("INSERT INTO booking_management_tokens (clinic_id, appointment_id, secret_hash, expires_at) VALUES (:clinic_id, :new_id, :secret_hash, :expires_at)"), {"clinic_id": session["clinic_id"], "new_id": replacement["id"], "secret_hash": hash_token(management_secret), "expires_at": starts_at + (old["ends_at"] - old["starts_at"]) + timedelta(days=30)})
    _audit(db, request, session, "appointment.reschedule", appointment_id)
    db.commit()
    return {"data": {"original_appointment_id": appointment_id, "replacement": dict(replacement), "management_secret": management_secret}, "meta": {"request_id": request.state.request_id}}


@availability_router.get("")
def public_availability(*, request: Request, clinic_slug: str = Query(min_length=1, max_length=120), branch_id: UUID = Query(), service_id: UUID = Query(), from_date: date = Query(), to_date: date = Query(), doctor_id: UUID | None = Query(default=None), db: Session = Depends(get_db)) -> dict:
    _validate_availability_range(from_date, to_date)
    clinic_id = db.execute(text("SELECT id FROM clinics WHERE slug = :slug AND archived_at IS NULL AND status = 'active'"), {"slug": clinic_slug.strip().casefold()}).scalar_one_or_none()
    if clinic_id is None:
        raise _error("NOT_FOUND", "Clinic not found.", status.HTTP_404_NOT_FOUND)
    set_tenant_context(db, clinic_id)
    branch = db.execute(text("SELECT id, timezone FROM branches WHERE clinic_id = :clinic_id AND id = :branch_id AND status = 'active' AND archived_at IS NULL"), {"clinic_id": clinic_id, "branch_id": branch_id}).mappings().one_or_none()
    service = db.execute(text("""
        SELECT s.id, s.duration_minutes, s.buffer_before_minutes, s.buffer_after_minutes
        FROM services s
        JOIN branch_services bs ON bs.clinic_id = s.clinic_id AND bs.service_id = s.id
        WHERE s.clinic_id = :clinic_id AND s.id = :service_id AND bs.branch_id = :branch_id
          AND s.status = 'active' AND s.archived_at IS NULL AND s.visibility = 'public'
    """), {"clinic_id": clinic_id, "service_id": service_id, "branch_id": branch_id}).mappings().one_or_none()
    if branch is None or service is None:
        raise _error("NOT_FOUND", "The requested booking option is not available.", status.HTTP_404_NOT_FOUND)
    if doctor_id is None:
        doctor_id = db.execute(text("""
            SELECT bd.doctor_id FROM branch_doctors bd
            JOIN doctor_profiles d ON d.clinic_id = bd.clinic_id AND d.id = bd.doctor_id
            JOIN doctor_services ds ON ds.clinic_id = bd.clinic_id AND ds.doctor_id = bd.doctor_id
            WHERE bd.clinic_id = :clinic_id AND bd.branch_id = :branch_id AND ds.service_id = :service_id
              AND d.status = 'active' AND d.archived_at IS NULL
            ORDER BY bd.doctor_id LIMIT 1
        """), {"clinic_id": clinic_id, "branch_id": branch_id, "service_id": service_id}).scalar_one_or_none()
    else:
        doctor_id = db.execute(text("""
            SELECT bd.doctor_id FROM branch_doctors bd
            JOIN doctor_profiles d ON d.clinic_id = bd.clinic_id AND d.id = bd.doctor_id
            JOIN doctor_services ds ON ds.clinic_id = bd.clinic_id AND ds.doctor_id = bd.doctor_id
            WHERE bd.clinic_id = :clinic_id AND bd.branch_id = :branch_id AND bd.doctor_id = :doctor_id AND ds.service_id = :service_id
              AND d.status = 'active' AND d.archived_at IS NULL
        """), {"clinic_id": clinic_id, "branch_id": branch_id, "doctor_id": doctor_id, "service_id": service_id}).scalar_one_or_none()
    if doctor_id is None:
        raise _error("NOT_FOUND", "The requested doctor or service is not available.", status.HTTP_404_NOT_FOUND)
    hours = db.execute(text("SELECT weekday, opens_at, closes_at FROM branch_hours WHERE clinic_id = :clinic_id AND branch_id = :branch_id AND is_closed = false AND opens_at IS NOT NULL AND closes_at IS NOT NULL"), {"clinic_id": clinic_id, "branch_id": branch_id}).mappings().all()
    rules = db.execute(text("SELECT weekday, starts_at, ends_at, effective_from, effective_to, slot_cadence_minutes FROM availability_rules WHERE clinic_id = :clinic_id AND branch_id = :branch_id AND doctor_id = :doctor_id AND (service_id IS NULL OR service_id = :service_id)"), {"clinic_id": clinic_id, "branch_id": branch_id, "doctor_id": doctor_id, "service_id": service_id}).mappings().all()
    holiday_rows = db.execute(text("""
        SELECT holiday_date, starts_at, ends_at
        FROM clinic_holidays
        WHERE clinic_id = :clinic_id
          AND holiday_date BETWEEN :from_date AND :to_date
          AND (branch_id IS NULL OR branch_id = :branch_id)
    """), {"clinic_id": clinic_id, "branch_id": branch_id, "from_date": from_date, "to_date": to_date}).mappings().all()
    holidays = {row["holiday_date"] for row in holiday_rows if row["starts_at"] is None and row["ends_at"] is None}
    holiday_blocks = [(row["holiday_date"], row["starts_at"], row["ends_at"]) for row in holiday_rows if row["starts_at"] is not None and row["ends_at"] is not None]
    busy = db.execute(text("SELECT occupancy_start, occupancy_end FROM appointments WHERE clinic_id = :clinic_id AND doctor_id = :doctor_id AND blocks_time = true AND status NOT IN ('cancelled', 'rescheduled') AND occupancy_end > :from_date::date AND occupancy_start < (:to_date::date + interval '1 day')"), {"clinic_id": clinic_id, "doctor_id": doctor_id, "from_date": from_date, "to_date": to_date}).all()
    busy.extend(db.execute(text("SELECT starts_at, ends_at FROM leave_blocks WHERE clinic_id = :clinic_id AND doctor_id = :doctor_id AND ends_at > :from_date::date AND starts_at < (:to_date::date + interval '1 day')"), {"clinic_id": clinic_id, "doctor_id": doctor_id, "from_date": from_date, "to_date": to_date}).all())
    busy.extend(db.execute(text("SELECT starts_at, ends_at FROM blocked_slots WHERE clinic_id = :clinic_id AND branch_id = :branch_id AND (doctor_id IS NULL OR doctor_id = :doctor_id) AND ends_at > :from_date::date AND starts_at < (:to_date::date + interval '1 day')"), {"clinic_id": clinic_id, "branch_id": branch_id, "doctor_id": doctor_id, "from_date": from_date, "to_date": to_date}).all())
    slots = generate_slots(start_date=from_date, end_date=to_date, timezone_name=branch["timezone"], branch_intervals=[AvailabilityInterval(r["weekday"], r["opens_at"], r["closes_at"]) for r in hours], doctor_intervals=[AvailabilityInterval(r["weekday"], r["starts_at"], r["ends_at"], r["effective_from"], r["effective_to"], r["slot_cadence_minutes"]) for r in rules], duration_minutes=service["duration_minutes"], buffer_before_minutes=service["buffer_before_minutes"], buffer_after_minutes=service["buffer_after_minutes"], busy_ranges=[(row[0], row[1]) for row in busy], holidays=holidays, holiday_blocks=holiday_blocks)
    db.commit()
    return {"data": {"slots": [slot.isoformat().replace("+00:00", "Z") for slot in slots]}, "meta": {"request_id": request.state.request_id, "timezone": branch["timezone"], "minimum_notice_minutes": 120}}


@question_router.get("")
def public_booking_questions(*, request: Request, clinic_slug: str = Query(min_length=1, max_length=120), service_id: UUID = Query(), db: Session = Depends(get_db)) -> dict:
    clinic_id = db.execute(text("SELECT id FROM clinics WHERE slug = :slug AND archived_at IS NULL AND status = 'active'"), {"slug": clinic_slug.strip().casefold()}).scalar_one_or_none()
    if clinic_id is None:
        raise _error("NOT_FOUND", "Clinic not found.", status.HTTP_404_NOT_FOUND)
    set_tenant_context(db, clinic_id)
    rows = db.execute(text("""
        SELECT q.id, q.prompt, q.input_type, q.options, q.required, sbq.position
        FROM service_booking_questions sbq
        JOIN booking_questions q ON q.clinic_id = sbq.clinic_id AND q.id = sbq.question_id
        JOIN services s ON s.clinic_id = sbq.clinic_id AND s.id = sbq.service_id
        WHERE sbq.clinic_id = :clinic_id AND sbq.service_id = :service_id
          AND q.active AND s.status = 'active' AND s.archived_at IS NULL AND s.visibility = 'public'
        ORDER BY sbq.position, q.id
    """), {"clinic_id": clinic_id, "service_id": service_id}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


def _normalize_email(value: str | None) -> str | None:
    return value.strip().casefold() if value else None


def _normalize_phone(value: str | None) -> str | None:
    return "".join(character for character in value if character.isdigit() or character == "+") if value else None


def _booking_unavailable(message: str = "The selected time is no longer available."):
    return _error("APPOINTMENT_UNAVAILABLE", message, status.HTTP_409_CONFLICT)


def _replay_idempotent_booking(db: Session, clinic_id: UUID, idempotency_key: str, body_hash: str, request: Request) -> dict | None:
    """Replay a committed booking after a concurrent unique-key race."""
    set_tenant_context(db, clinic_id)
    existing = db.execute(
        text("SELECT id, reference, status, idempotency_body_hash FROM appointments WHERE clinic_id = :clinic_id AND idempotency_key = :key"),
        {"clinic_id": clinic_id, "key": idempotency_key},
    ).mappings().one_or_none()
    if existing is None:
        return None
    if existing["idempotency_body_hash"] != body_hash:
        raise _error("IDEMPOTENCY_MISMATCH", "This idempotency key was already used with different data.", status.HTTP_409_CONFLICT)
    db.commit()
    return {"data": {"reference": existing["reference"], "status": existing["status"]}, "meta": {"request_id": request.state.request_id}}


def _clock_value(value: object) -> time | None:
    if isinstance(value, time):
        return value
    if isinstance(value, str):
        try:
            return time.fromisoformat(value)
        except ValueError:
            return None
    return None


def _validate_commit_time(*, db: Session, clinic_id: UUID, branch_id: UUID, doctor_id: UUID, service_id: UUID, branch_timezone: str, starts_at: datetime, ends_at: datetime, occupancy_start: datetime, occupancy_end: datetime, exclude_appointment_id: UUID | None = None) -> None:
    """Re-evaluate all non-constraint scheduling rules in the booking transaction.

    Availability responses are advisory. This check is deliberately repeated immediately
    before the insert; the exclusion constraint remains the final concurrency authority.
    """
    try:
        zone = ZoneInfo(branch_timezone)
    except Exception as exc:
        raise _error("INTERNAL_ERROR", "The branch timezone is not configured correctly.", status.HTTP_500_INTERNAL_SERVER_ERROR) from exc

    start_utc = starts_at.astimezone(timezone.utc)
    now_utc = datetime.now(timezone.utc)
    local_start = start_utc.astimezone(zone)
    local_end = ends_at.astimezone(timezone.utc).astimezone(zone)
    local_occupancy_start = occupancy_start.astimezone(timezone.utc).astimezone(zone)
    local_occupancy_end = occupancy_end.astimezone(timezone.utc).astimezone(zone)
    today = now_utc.astimezone(zone).date()
    if start_utc < now_utc + timedelta(minutes=120):
        raise _booking_unavailable("The appointment does not meet the minimum booking notice.")
    if local_start.date() < today or (local_start.date() - today).days > 89:
        raise _booking_unavailable("The appointment is outside the booking window.")
    if local_start.date() != local_end.date() or local_occupancy_start.date() != local_occupancy_end.date():
        raise _booking_unavailable("The appointment must fit within one local calendar day.")

    params = {"clinic_id": clinic_id, "branch_id": branch_id, "doctor_id": doctor_id, "service_id": service_id, "day": local_start.date(), "exclude_appointment_id": exclude_appointment_id}
    hours = db.execute(text("""
        SELECT opens_at, closes_at, breaks
        FROM branch_hours
        WHERE clinic_id = :clinic_id AND branch_id = :branch_id
          AND weekday = :weekday AND is_closed = false
          AND opens_at IS NOT NULL AND closes_at IS NOT NULL
        FOR SHARE
    """), {**params, "weekday": local_start.weekday()}).mappings().all()
    def _hour_contains(row: dict) -> bool:
        opens_at, closes_at = _clock_value(row["opens_at"]), _clock_value(row["closes_at"])
        if opens_at is None or closes_at is None or not (opens_at <= local_start.time() and closes_at >= local_end.time()):
            return False
        for item in row["breaks"] or []:
            if not isinstance(item, dict):
                continue
            break_start, break_end = _clock_value(item.get("starts_at")), _clock_value(item.get("ends_at"))
            if break_start and break_end and local_start.time() < break_end and local_end.time() > break_start:
                return False
        return True

    if not any(_hour_contains(row) for row in hours):
        raise _booking_unavailable("The appointment is outside branch hours.")

    rules = db.execute(text("""
        SELECT starts_at, ends_at
        FROM availability_rules
        WHERE clinic_id = :clinic_id AND branch_id = :branch_id AND doctor_id = :doctor_id
          AND weekday = :weekday AND effective_from <= :day
          AND (effective_to IS NULL OR effective_to >= :day)
          AND (service_id IS NULL OR service_id = :service_id)
        FOR SHARE
    """), {**params, "weekday": local_start.weekday()}).mappings().all()
    if not any(row["starts_at"] <= local_start.time() and row["ends_at"] >= local_end.time() for row in rules):
        raise _booking_unavailable("The appointment is outside the doctor's availability.")

    holidays = db.execute(text("""
        SELECT starts_at, ends_at
        FROM clinic_holidays
        WHERE clinic_id = :clinic_id AND holiday_date = :day
          AND (branch_id IS NULL OR branch_id = :branch_id)
        FOR SHARE
    """), params).mappings().all()
    for holiday in holidays:
        if holiday["starts_at"] is None:
            raise _booking_unavailable("The selected day is closed for bookings.")
        if local_occupancy_start.time() < holiday["ends_at"] and local_occupancy_end.time() > holiday["starts_at"]:
            raise _booking_unavailable("The selected time is closed for bookings.")

    leave = db.execute(text("""
        SELECT 1 FROM leave_blocks
        WHERE clinic_id = :clinic_id AND doctor_id = :doctor_id
          AND (branch_id IS NULL OR branch_id = :branch_id)
          AND ends_at > :occupancy_start AND starts_at < :occupancy_end
        LIMIT 1
    """), {**params, "occupancy_start": occupancy_start, "occupancy_end": occupancy_end}).scalar_one_or_none()
    blocked = db.execute(text("""
        SELECT 1 FROM blocked_slots
        WHERE clinic_id = :clinic_id AND branch_id = :branch_id
          AND (doctor_id IS NULL OR doctor_id = :doctor_id)
          AND ends_at > :occupancy_start AND starts_at < :occupancy_end
        LIMIT 1
    """), {**params, "occupancy_start": occupancy_start, "occupancy_end": occupancy_end}).scalar_one_or_none()
    busy = db.execute(text("""
        SELECT 1 FROM appointments
        WHERE clinic_id = :clinic_id AND doctor_id = :doctor_id AND blocks_time = true
          AND (:exclude_appointment_id IS NULL OR id <> :exclude_appointment_id)
          AND status NOT IN ('cancelled', 'rescheduled')
          AND occupancy_end > :occupancy_start AND occupancy_start < :occupancy_end
        LIMIT 1
    """), {**params, "occupancy_start": occupancy_start, "occupancy_end": occupancy_end}).scalar_one_or_none()
    if leave or blocked or busy:
        raise _booking_unavailable()


@router.post("", status_code=status.HTTP_201_CREATED)
def create_public_booking(payload: PublicBookingRequest, request: Request, db: Session = Depends(get_db), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), clinic_slug: str | None = Header(default=None, alias="X-Clinic-Slug")) -> dict:
    if not idempotency_key or len(idempotency_key) > 128:
        raise _error("INVALID_INPUT", "Idempotency-Key is required.", status.HTTP_400_BAD_REQUEST)
    if not clinic_slug:
        raise _error("INVALID_INPUT", "Clinic resolution is required.", status.HTTP_400_BAD_REQUEST)
    clinic_id = db.execute(text("SELECT id FROM clinics WHERE slug = :slug AND archived_at IS NULL AND status = 'active'"), {"slug": clinic_slug.strip().casefold()}).scalar_one_or_none()
    if clinic_id is None:
        raise _error("NOT_FOUND", "Clinic not found.", status.HTTP_404_NOT_FOUND)
    set_tenant_context(db, clinic_id)
    raw_body = payload.model_dump(mode="json")
    body_hash = hashlib.sha256(json.dumps(raw_body, sort_keys=True).encode()).hexdigest()
    existing = db.execute(text("SELECT id, reference, status FROM appointments WHERE clinic_id = :clinic_id AND idempotency_key = :key"), {"clinic_id": clinic_id, "key": idempotency_key}).mappings().one_or_none()
    if existing:
        if db.execute(text("SELECT idempotency_body_hash FROM appointments WHERE id = :id"), {"id": existing["id"]}).scalar_one() != body_hash:
            raise _error("IDEMPOTENCY_MISMATCH", "This idempotency key was already used with different data.", status.HTTP_409_CONFLICT)
        db.commit()
        return {"data": {"reference": existing["reference"], "status": existing["status"]}, "meta": {"request_id": request.state.request_id}}
    service = db.execute(text("""
        SELECT s.id, s.duration_minutes, s.buffer_before_minutes, s.buffer_after_minutes
        FROM services s
        JOIN branch_services bs ON bs.clinic_id = s.clinic_id AND bs.service_id = s.id
        WHERE s.clinic_id = :clinic_id AND s.id = :service_id AND bs.branch_id = :branch_id
          AND s.status = 'active' AND s.archived_at IS NULL AND s.visibility = 'public'
    """), {"clinic_id": clinic_id, "service_id": payload.service_id, "branch_id": payload.branch_id}).mappings().one_or_none()
    branch = db.execute(text("SELECT id, timezone FROM branches WHERE clinic_id = :clinic_id AND id = :branch_id AND status = 'active' AND archived_at IS NULL"), {"clinic_id": clinic_id, "branch_id": payload.branch_id}).mappings().one_or_none()
    if service is None or branch is None:
        raise _error("NOT_FOUND", "The requested booking option is not available.", status.HTTP_404_NOT_FOUND)
    if payload.starts_at.tzinfo is None:
        raise _error("INVALID_INPUT", "starts_at must include a timezone offset.", status.HTTP_400_BAD_REQUEST)
    if payload.doctor_id is None:
        doctor_id = db.execute(text("""
            SELECT bd.doctor_id FROM branch_doctors bd
            JOIN doctor_profiles d ON d.clinic_id = bd.clinic_id AND d.id = bd.doctor_id
            JOIN doctor_services ds ON ds.clinic_id = bd.clinic_id AND ds.doctor_id = bd.doctor_id
            WHERE bd.clinic_id = :clinic_id AND bd.branch_id = :branch_id AND ds.service_id = :service_id
              AND d.status = 'active' AND d.archived_at IS NULL
            ORDER BY bd.doctor_id LIMIT 1
        """), {"clinic_id": clinic_id, "branch_id": payload.branch_id, "service_id": payload.service_id}).scalar_one_or_none()
    else:
        doctor_id = db.execute(text("""
            SELECT bd.doctor_id FROM branch_doctors bd
            JOIN doctor_profiles d ON d.clinic_id = bd.clinic_id AND d.id = bd.doctor_id
            JOIN doctor_services ds ON ds.clinic_id = bd.clinic_id AND ds.doctor_id = bd.doctor_id
            WHERE bd.clinic_id = :clinic_id AND bd.branch_id = :branch_id AND bd.doctor_id = :doctor_id AND ds.service_id = :service_id
              AND d.status = 'active' AND d.archived_at IS NULL
        """), {"clinic_id": clinic_id, "branch_id": payload.branch_id, "doctor_id": payload.doctor_id, "service_id": payload.service_id}).scalar_one_or_none()
    if doctor_id is None:
        raise _error("NOT_FOUND", "The requested doctor or service is not available at this branch.", status.HTTP_404_NOT_FOUND)
    question_rows = db.execute(text("""
        SELECT q.id, q.input_type, q.options, q.required
        FROM service_booking_questions sbq
        JOIN booking_questions q ON q.clinic_id = sbq.clinic_id AND q.id = sbq.question_id
        WHERE sbq.clinic_id = :clinic_id AND sbq.service_id = :service_id AND q.active
    """), {"clinic_id": clinic_id, "service_id": payload.service_id}).mappings().all()
    supplied = {answer.question_id: answer.value.strip() for answer in payload.answers}
    known_ids = {row["id"] for row in question_rows}
    if len(supplied) != len(payload.answers) or any(row["required"] and not supplied.get(row["id"]) for row in question_rows) or any(question_id not in known_ids for question_id in supplied):
        raise _error("INVALID_INPUT", "Booking answers must match the active questions for this service.", status.HTTP_400_BAD_REQUEST)
    for row in question_rows:
        value = supplied.get(row["id"])
        if value is None:
            continue
        if row["input_type"] == "yes_no" and value not in {"yes", "no"}:
            raise _error("INVALID_INPUT", "Yes/no booking answers must be yes or no.", status.HTTP_400_BAD_REQUEST)
        if row["input_type"] == "choice" and value not in (row["options"] or []):
            raise _error("INVALID_INPUT", "The selected booking answer is not available.", status.HTTP_400_BAD_REQUEST)
    # Normalize persistence and duration arithmetic to UTC. Branch-local rules are
    # evaluated by _validate_commit_time after converting these instants back to
    # the branch IANA timezone.
    starts_at = payload.starts_at.astimezone(timezone.utc)
    ends_at = starts_at + timedelta(minutes=service["duration_minutes"])
    occupancy_start = starts_at - timedelta(minutes=service["buffer_before_minutes"])
    occupancy_end = ends_at + timedelta(minutes=service["buffer_after_minutes"])
    _validate_commit_time(
        db=db,
        clinic_id=clinic_id,
        branch_id=payload.branch_id,
        doctor_id=doctor_id,
        service_id=payload.service_id,
        branch_timezone=branch["timezone"],
        starts_at=starts_at,
        ends_at=ends_at,
        occupancy_start=occupancy_start,
        occupancy_end=occupancy_end,
    )
    normalized_email = _normalize_email(payload.email)
    normalized_phone = _normalize_phone(payload.phone)
    patient = db.execute(text("SELECT id FROM patients WHERE clinic_id = :clinic_id AND ((:email IS NOT NULL AND normalized_email = :email) OR (:phone IS NOT NULL AND normalized_phone = :phone)) ORDER BY created_at LIMIT 1"), {"clinic_id": clinic_id, "email": normalized_email, "phone": normalized_phone}).scalar_one_or_none()
    if patient is None:
        patient = db.execute(text("INSERT INTO patients (clinic_id, patient_number, full_name, normalized_email, normalized_phone, date_of_birth) VALUES (:clinic_id, :patient_number, :full_name, :email, :phone, :dob) RETURNING id"), {"clinic_id": clinic_id, "patient_number": f"P-{secrets.token_hex(6).upper()}", "full_name": payload.full_name.strip(), "email": normalized_email, "phone": normalized_phone, "dob": payload.date_of_birth}).scalar_one()
    reference = f"BK-{secrets.token_hex(5).upper()}"
    try:
        appointment = db.execute(text("""
            INSERT INTO appointments (clinic_id, branch_id, doctor_id, service_id, patient_id, starts_at, ends_at, occupancy_start, occupancy_end, reference, idempotency_key, idempotency_body_hash, policy_snapshot)
            VALUES (:clinic_id, :branch_id, :doctor_id, :service_id, :patient_id, :starts_at, :ends_at, :occupancy_start, :occupancy_end, :reference, :idempotency_key, :body_hash, CAST(:policy AS jsonb))
            RETURNING id, reference, status
        """), {"clinic_id": clinic_id, "branch_id": payload.branch_id, "doctor_id": doctor_id, "service_id": payload.service_id, "patient_id": patient, "starts_at": starts_at, "ends_at": ends_at, "occupancy_start": occupancy_start, "occupancy_end": occupancy_end, "reference": reference, "idempotency_key": idempotency_key, "body_hash": body_hash, "policy": json.dumps({"duration_minutes": service["duration_minutes"], "buffer_before_minutes": service["buffer_before_minutes"], "buffer_after_minutes": service["buffer_after_minutes"], "branch_timezone": branch["timezone"]})}).mappings().one()
        secret = secrets.token_urlsafe(32)
        db.execute(text("INSERT INTO appointment_history (clinic_id, appointment_id, to_status) VALUES (:clinic_id, :appointment_id, 'requested')"), {"clinic_id": clinic_id, "appointment_id": appointment["id"]})
        for question_id, value in supplied.items():
            db.execute(text("INSERT INTO appointment_answers (clinic_id, appointment_id, question_id, answer) VALUES (:clinic_id, :appointment_id, :question_id, CAST(:answer AS jsonb))"), {"clinic_id": clinic_id, "appointment_id": appointment["id"], "question_id": question_id, "answer": json.dumps(value)})
        db.execute(text("INSERT INTO booking_management_tokens (clinic_id, appointment_id, secret_hash, expires_at) VALUES (:clinic_id, :appointment_id, :secret_hash, :expires_at)"), {"clinic_id": clinic_id, "appointment_id": appointment["id"], "secret_hash": hash_token(secret), "expires_at": ends_at + timedelta(days=30)})
        record_event(
            db,
            clinic_id=clinic_id,
            actor_user_id=None,
            action="public_appointment.create",
            entity_type="appointment",
            entity_id=appointment["id"],
            outcome="success",
            request_id=UUID(request.state.request_id),
            metadata={"source": "public", "service_id": str(payload.service_id), "branch_id": str(payload.branch_id)},
        )
        db.commit()
        return {"data": {"reference": appointment["reference"], "status": appointment["status"], "management_secret": secret}, "meta": {"request_id": request.state.request_id}}
    except IntegrityError as exc:
        db.rollback()
        if "uq_appointments_idempotency" in str(exc):
            replay = _replay_idempotent_booking(db, clinic_id, idempotency_key, body_hash, request)
            if replay is not None:
                return replay
        if "no_doctor_overlap" in str(exc):
            raise _error("APPOINTMENT_CONFLICT", "The selected time is no longer available.", status.HTTP_409_CONFLICT) from exc
        raise
    except Exception as exc:
        db.rollback()
        if "no_doctor_overlap" in str(exc):
            raise _error("APPOINTMENT_CONFLICT", "The selected time is no longer available.", status.HTTP_409_CONFLICT) from exc
        raise

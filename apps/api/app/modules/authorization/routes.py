from fastapi import APIRouter, Cookie, Depends, Header, Request, status
from fastapi import APIRouter, Cookie, Depends, Request, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.db.session import get_db
from app.db.tenant import set_tenant_context
from app.modules.authorization.service import ForbiddenError, require_permission
from app.modules.audit.service import record_event
from app.modules.authorization.schemas import ClinicStatusUpdate, ClinicUpdate
from app.modules.identity.routes import _error, _session_or_401, _validate_origin
from app.modules.identity.service import SessionError, verify_csrf

router = APIRouter(prefix="/api/v1/clinic", tags=["clinic"])


def _clinic_read(request: Request, db: Session, session_token: str | None) -> dict:
    session = _session_or_401(db, session_token)
    if session["clinic_id"] is None:
        raise _error("FORBIDDEN", "You do not have access to a clinic.", status.HTTP_403_FORBIDDEN)
    set_tenant_context(db, session["clinic_id"], session["user_id"])
    try:
        require_permission(db, session["user_id"], session["clinic_id"], "clinic.read")
    except ForbiddenError as exc:
        raise _error("FORBIDDEN", "You do not have permission to read this clinic.", status.HTTP_403_FORBIDDEN) from exc
    clinic = db.execute(text("SELECT id, name, slug, status, timezone, locale, version, created_at, updated_at FROM clinics WHERE id = :id AND archived_at IS NULL"), {"id": session["clinic_id"]}).mappings().one_or_none()
    if clinic is None:
        raise _error("NOT_FOUND", "Clinic not found.", status.HTTP_404_NOT_FOUND)
    return {"data": dict(clinic), "meta": {"request_id": request.state.request_id}}


@router.get("")
def clinic_get(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    result = _clinic_read(request, db, session_token)
    db.commit()
    return result


@router.get("/context")
def clinic_context(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    result = _clinic_read(request, db, session_token)
    db.commit()
    return result


def _write_context(request: Request, db: Session, session_token: str | None, permission: str, csrf_token: str | None) -> dict:
    _validate_origin(request)
    session = _session_or_401(db, session_token)
    if session["clinic_id"] is None:
        raise _error("FORBIDDEN", "A clinic context is required.", status.HTTP_403_FORBIDDEN)
    set_tenant_context(db, session["clinic_id"], session["user_id"])
    if not csrf_token:
        raise _error("CSRF_REQUIRED", "A CSRF token is required.", status.HTTP_403_FORBIDDEN)
    try:
        verify_csrf(session, csrf_token)
        require_permission(db, session["user_id"], session["clinic_id"], permission)
    except SessionError as exc:
        raise _error("CSRF_INVALID", "The CSRF token is invalid.", status.HTTP_403_FORBIDDEN) from exc
    except ForbiddenError as exc:
        raise _error("FORBIDDEN", "You do not have permission for this clinic command.", status.HTTP_403_FORBIDDEN) from exc
    return session


def _onboarding_state(db: Session, clinic_id) -> dict:
    row = db.execute(text("""
        SELECT c.onboarding_completed_at,
               EXISTS (SELECT 1 FROM branches b WHERE b.clinic_id = c.id AND b.status = 'active' AND b.archived_at IS NULL) AS first_branch,
               EXISTS (SELECT 1 FROM branch_hours h JOIN branches b ON b.clinic_id = h.clinic_id AND b.id = h.branch_id WHERE h.clinic_id = c.id AND b.status = 'active' AND h.is_closed = false) AS branch_hours,
               EXISTS (SELECT 1 FROM doctor_profiles d WHERE d.clinic_id = c.id AND d.status = 'active' AND d.archived_at IS NULL) AS doctor,
               EXISTS (SELECT 1 FROM services s WHERE s.clinic_id = c.id AND s.status = 'active' AND s.archived_at IS NULL) AS service,
               EXISTS (SELECT 1 FROM branch_doctors bd WHERE bd.clinic_id = c.id) AS doctor_assignment,
               EXISTS (SELECT 1 FROM branch_services bs WHERE bs.clinic_id = c.id) AS service_assignment
        FROM clinics c WHERE c.id = :clinic_id
    """), {"clinic_id": clinic_id}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Clinic not found.", status.HTTP_404_NOT_FOUND)
    steps = {key: bool(row[key]) for key in ("first_branch", "branch_hours", "doctor", "service", "doctor_assignment", "service_assignment")}
    return {"completed": bool(row["onboarding_completed_at"]), "completed_at": row["onboarding_completed_at"], "steps": steps, "ready_to_complete": all(steps.values())}


@router.get("/onboarding")
def onboarding_status(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _session_or_401(db, session_token)
    if session["clinic_id"] is None:
        raise _error("FORBIDDEN", "A clinic context is required.", status.HTTP_403_FORBIDDEN)
    set_tenant_context(db, session["clinic_id"], session["user_id"])
    try:
        require_permission(db, session["user_id"], session["clinic_id"], "clinic.read")
    except ForbiddenError as exc:
        raise _error("FORBIDDEN", "You do not have permission to read this clinic.", status.HTTP_403_FORBIDDEN) from exc
    state = _onboarding_state(db, session["clinic_id"])
    db.commit()
    return {"data": state, "meta": {"request_id": request.state.request_id}}


@router.post("/onboarding/complete")
def complete_onboarding(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_context(request, db, session_token, "clinic.update", csrf_token)
    state = _onboarding_state(db, session["clinic_id"])
    if not state["ready_to_complete"] and not state["completed"]:
        missing = [key for key, value in state["steps"].items() if not value]
        raise _error("SETUP_INCOMPLETE", "Complete the required clinic setup steps before continuing.", status.HTTP_409_CONFLICT, fields={"missing_steps": missing})
    row = db.execute(text("UPDATE clinics SET onboarding_completed_at = COALESCE(onboarding_completed_at, now()), updated_at = now(), version = version + 1 WHERE id = :clinic_id RETURNING onboarding_completed_at, version"), {"clinic_id": session["clinic_id"]}).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="clinic.onboarding_complete", entity_type="clinic", entity_id=session["clinic_id"], outcome="success", request_id=__import__("uuid").UUID(request.state.request_id))
    db.commit()
    return {"data": {"completed": True, "completed_at": row["onboarding_completed_at"], "version": row["version"]}, "meta": {"request_id": request.state.request_id}}


@router.patch("")
def clinic_update(payload: ClinicUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_context(request, db, session_token, "clinic.update", csrf_token)
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    if not values:
        raise _error("INVALID_INPUT", "At least one clinic field is required.", status.HTTP_400_BAD_REQUEST)
    if "timezone" in values:
        try:
            ZoneInfo(values["timezone"])
        except ZoneInfoNotFoundError as exc:
            raise _error("INVALID_INPUT", "The clinic timezone must be a valid IANA timezone.", status.HTTP_400_BAD_REQUEST) from exc
    updates = ", ".join(f"{field} = :{field}" for field in values)
    params = {"clinic_id": session["clinic_id"], "expected_version": payload.expected_version, **values}
    try:
        row = db.execute(text(f"UPDATE clinics SET {updates}, version = version + 1, updated_at = now() WHERE id = :clinic_id AND version = :expected_version AND archived_at IS NULL RETURNING id, name, slug, status, timezone, locale, version, updated_at"), params).mappings().one_or_none()
    except IntegrityError as exc:
        db.rollback()
        raise _error("DUPLICATE", "The clinic slug is already in use.", status.HTTP_409_CONFLICT) from exc
    if row is None:
        raise _error("VERSION_CONFLICT", "The clinic changed before this update.", status.HTTP_409_CONFLICT)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="clinic.update", entity_type="clinic", entity_id=session["clinic_id"], outcome="success", request_id=__import__("uuid").UUID(request.state.request_id), metadata={"fields": sorted(values)})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.post("/status")
def clinic_status(payload: ClinicStatusUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_context(request, db, session_token, "admin.clinic.manage", csrf_token)
    row = db.execute(text("UPDATE clinics SET status = :status, archived_at = CASE WHEN :status = 'archived' THEN now() ELSE archived_at END, version = version + 1, updated_at = now() WHERE id = :clinic_id AND version = :expected_version RETURNING id, status, archived_at, version, updated_at"), {"clinic_id": session["clinic_id"], "status": payload.status, "expected_version": payload.expected_version}).mappings().one_or_none()
    if row is None:
        raise _error("VERSION_CONFLICT", "The clinic changed before this command.", status.HTTP_409_CONFLICT)
    if payload.status != "active":
        db.execute(text("UPDATE sessions SET revoked_at = now() WHERE user_id IN (SELECT id FROM users WHERE clinic_id = :clinic_id) AND revoked_at IS NULL"), {"clinic_id": session["clinic_id"]})
        db.execute(text("UPDATE booking_management_tokens SET revoked_at = now() WHERE clinic_id = :clinic_id AND revoked_at IS NULL"), {"clinic_id": session["clinic_id"]})
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="clinic.status_change", entity_type="clinic", entity_id=session["clinic_id"], outcome="success", request_id=__import__("uuid").UUID(request.state.request_id), metadata={"status": payload.status})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}

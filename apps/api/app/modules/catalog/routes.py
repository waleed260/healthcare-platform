from datetime import date, time

from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.tenant import set_tenant_context
from app.modules.authorization.service import ForbiddenError, require_permission
from app.modules.catalog.schemas import BranchCreate, BranchHoursUpsert, BranchUpdate, CatalogStatusUpdate, DoctorCreate, DoctorUpdate, HolidayCreate, ResourceCreate, ResourceUpdate, RoomCreate, RoomUpdate, ServiceCreate, ServiceUpdate
from app.modules.identity.routes import _error, _session_or_401, _validate_origin
from app.modules.identity.service import SessionError, verify_csrf
from app.modules.audit.service import record_event
from app.core.security import decode_cursor, encode_cursor

router = APIRouter(prefix="/api/v1/services", tags=["services"])
catalog_router = APIRouter(prefix="/api/v1", tags=["catalog"])


def _authorized(db: Session, session_token: str | None, permission: str, branch_id: str | None = None) -> dict:
    session = _session_or_401(db, session_token)
    if session["clinic_id"] is None:
        raise _error("FORBIDDEN", "A clinic context is required.", status.HTTP_403_FORBIDDEN)
    set_tenant_context(db, session["clinic_id"], session["user_id"])
    try:
        require_permission(db, session["user_id"], session["clinic_id"], permission, branch_id=branch_id)
    except ForbiddenError as exc:
        raise _error("FORBIDDEN", "You do not have permission for this service.", status.HTTP_403_FORBIDDEN) from exc
    return session


def _write_authorized(db: Session, request: Request, session_token: str | None, permission: str, csrf_token: str | None, branch_id: str | None = None) -> dict:
    _validate_origin(request)
    session = _authorized(db, session_token, permission, branch_id=branch_id)
    if not csrf_token:
        raise _error("CSRF_REQUIRED", "A CSRF token is required.", status.HTTP_403_FORBIDDEN)
    try:
        verify_csrf(session, csrf_token)
    except SessionError as exc:
        raise _error("CSRF_INVALID", "The CSRF token is invalid.", status.HTTP_403_FORBIDDEN) from exc
    return session


@catalog_router.get("/branches")
def list_branches(request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "branch.read")
    cursor_values = decode_cursor(cursor, "branches") if cursor else None
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    try:
        after_name = cursor_values["name"] if cursor_values else None
        after_id = cursor_values["id"] if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT id, code, name, timezone, address, phone, status, version, created_at, updated_at
        FROM branches
        WHERE clinic_id = :clinic_id AND archived_at IS NULL
          AND (
            NOT EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id)
            OR EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id AND s.branch_id = branches.id)
          )
          AND (:after_name IS NULL OR name > :after_name OR (name = :after_name AND id > :after_id))
        ORDER BY name, id
        LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "after_name": after_name, "after_id": after_id, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor("branches", {"name": rows[-1]["name"], "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@catalog_router.post("/branches", status_code=status.HTTP_201_CREATED)
def create_branch(payload: BranchCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "branch.manage", csrf_token)
    try:
        row = db.execute(text("INSERT INTO branches (clinic_id, code, name, timezone, address, phone) VALUES (:clinic_id, :code, :name, :timezone, CAST(:address AS jsonb), :phone) RETURNING id, code, name, timezone, address, phone, status, version"), {"clinic_id": session["clinic_id"], "code": payload.code.strip().casefold(), "name": payload.name.strip(), "timezone": payload.timezone, "address": __import__("json").dumps(payload.address), "phone": payload.phone}).mappings().one()
    except Exception as exc:
        db.rollback()
        if "uq_branches_clinic_code" in str(exc):
            raise _error("DUPLICATE", "A branch with this code already exists.", status.HTTP_409_CONFLICT) from exc
        raise
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@catalog_router.patch("/branches/{branch_id}")
def update_branch(branch_id: str, payload: BranchUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "branch.manage", csrf_token, branch_id=branch_id)
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    if ("code" in values and values["code"] is None) or ("name" in values and values["name"] is None):
        raise _error("INVALID_INPUT", "Branch code and name cannot be cleared.", status.HTTP_400_BAD_REQUEST)
    if "code" in values:
        values["code"] = values["code"].strip().casefold()
    if "name" in values:
        values["name"] = values["name"].strip()
    if "address" in values:
        values["address"] = __import__("json").dumps(values["address"])
    assignments = []
    parameters = {"clinic_id": session["clinic_id"], "branch_id": branch_id, "expected_version": payload.expected_version}
    for field in ("code", "name", "timezone", "address", "phone"):
        if field in values:
            assignments.append(f"{field} = CAST(:{field} AS jsonb)" if field == "address" else f"{field} = :{field}")
            parameters[field] = values[field]
    try:
        row = db.execute(text(f"""
            UPDATE branches SET {', '.join(assignments)}, version = version + 1, updated_at = now()
            WHERE clinic_id = :clinic_id AND id = :branch_id AND archived_at IS NULL AND version = :expected_version
            RETURNING id, code, name, timezone, address, phone, status, version, updated_at
        """), parameters).mappings().one_or_none()
    except Exception as exc:
        db.rollback()
        if "uq_branches_clinic_code" in str(exc):
            raise _error("DUPLICATE", "A branch with this code already exists.", status.HTTP_409_CONFLICT) from exc
        raise
    if row is None:
        exists = db.execute(text("SELECT version FROM branches WHERE clinic_id = :clinic_id AND id = :branch_id AND archived_at IS NULL"), parameters).scalar_one_or_none()
        if exists is None:
            raise _error("NOT_FOUND", "Branch not found.", status.HTTP_404_NOT_FOUND)
        raise _error("VERSION_CONFLICT", "The branch changed before this update.", status.HTTP_409_CONFLICT)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="branch.update", entity_type="branch", entity_id=row["id"], outcome="success", request_id=__import__("uuid").UUID(request.state.request_id), metadata={"fields": sorted(values)})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@catalog_router.post("/branches/{branch_id}/status")
def branch_status(branch_id: str, payload: CatalogStatusUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "branch.manage", csrf_token, branch_id=branch_id)
    row = db.execute(text("""
        UPDATE branches SET status = :status, archived_at = CASE WHEN :status = 'archived' THEN COALESCE(archived_at, now()) ELSE NULL END,
            version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :branch_id
        RETURNING id, code, name, status, version, archived_at, updated_at
    """), {"clinic_id": session["clinic_id"], "branch_id": branch_id, "status": payload.status}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Branch not found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="branch.status_change", entity_type="branch", entity_id=row["id"], outcome="success", request_id=__import__("uuid").UUID(request.state.request_id), metadata={"status": payload.status})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@catalog_router.put("/branches/{branch_id}/hours/{weekday}")
def upsert_branch_hours(branch_id: str, weekday: int, payload: BranchHoursUpsert, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "schedule.manage", csrf_token, branch_id=branch_id)
    if weekday != payload.weekday:
        raise _error("INVALID_INPUT", "The weekday path and body must match.", status.HTTP_400_BAD_REQUEST)
    if not payload.is_closed and (payload.opens_at is None or payload.closes_at is None or payload.opens_at >= payload.closes_at):
        raise _error("INVALID_INPUT", "Open hours require an ordered opening and closing time.", status.HTTP_400_BAD_REQUEST)
    row = db.execute(text("""
        INSERT INTO branch_hours (clinic_id, branch_id, weekday, interval_index, opens_at, closes_at, is_closed)
        VALUES (:clinic_id, :branch_id, :weekday, :interval_index, :opens_at, :closes_at, :is_closed)
        ON CONFLICT (clinic_id, branch_id, weekday, interval_index) DO UPDATE SET opens_at = EXCLUDED.opens_at, closes_at = EXCLUDED.closes_at, is_closed = EXCLUDED.is_closed, updated_at = now()
        RETURNING id, branch_id, weekday, opens_at, closes_at, is_closed, updated_at
    """), {"clinic_id": session["clinic_id"], "branch_id": branch_id, **payload.model_dump()}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Branch not found.", status.HTTP_404_NOT_FOUND)
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@catalog_router.get("/branches/{branch_id}/hours")
def list_branch_hours(branch_id: str, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "schedule.read", branch_id=branch_id)
    rows = db.execute(text("SELECT id, branch_id, weekday, interval_index, opens_at, closes_at, is_closed, breaks, updated_at FROM branch_hours WHERE clinic_id = :clinic_id AND branch_id = :branch_id ORDER BY weekday, interval_index, id"), {"clinic_id": session["clinic_id"], "branch_id": branch_id}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@catalog_router.get("/doctors")
def list_doctors(request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "doctor.read")
    cursor_values = decode_cursor(cursor, "doctors") if cursor else None
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    try:
        after_name = cursor_values["name"] if cursor_values else None
        after_id = cursor_values["id"] if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT id, public_name, specialty, registration, verification_status, bio, consultation_duration_minutes, status, version, created_at, updated_at
        FROM doctor_profiles
        WHERE clinic_id = :clinic_id AND archived_at IS NULL
          AND (NOT EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id)
               OR EXISTS (SELECT 1 FROM branch_doctors bd JOIN user_branch_scopes s ON s.clinic_id = bd.clinic_id AND s.branch_id = bd.branch_id WHERE bd.clinic_id = :clinic_id AND bd.doctor_id = doctor_profiles.id AND s.user_id = :user_id))
          AND (:after_name IS NULL OR public_name > :after_name OR (public_name = :after_name AND id > :after_id))
        ORDER BY public_name, id
        LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "after_name": after_name, "after_id": after_id, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor("doctors", {"name": rows[-1]["public_name"], "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@catalog_router.post("/doctors", status_code=status.HTTP_201_CREATED)
def create_doctor(payload: DoctorCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "doctor.manage", csrf_token)
    row = db.execute(text("INSERT INTO doctor_profiles (clinic_id, public_name, specialty, registration, bio, consultation_duration_minutes) VALUES (:clinic_id, :public_name, :specialty, :registration, :bio, :duration) RETURNING id, public_name, specialty, registration, verification_status, bio, consultation_duration_minutes, status, version"), {"clinic_id": session["clinic_id"], "duration": payload.consultation_duration_minutes, **payload.model_dump(exclude={"consultation_duration_minutes"})}).mappings().one()
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@catalog_router.patch("/doctors/{doctor_id}")
def update_doctor(doctor_id: str, payload: DoctorUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "doctor.manage", csrf_token)
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    if "public_name" in values and values["public_name"] is None:
        raise _error("INVALID_INPUT", "Doctor name cannot be cleared.", status.HTTP_400_BAD_REQUEST)
    if "public_name" in values:
        values["public_name"] = values["public_name"].strip()
    fields = ("public_name", "specialty", "registration", "bio", "consultation_duration_minutes")
    row = db.execute(text(f"""
        UPDATE doctor_profiles SET {', '.join(f'{field} = :{field}' for field in values)}, version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :doctor_id AND archived_at IS NULL AND version = :expected_version
          AND (NOT EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id)
               OR EXISTS (SELECT 1 FROM branch_doctors bd JOIN user_branch_scopes s ON s.clinic_id = bd.clinic_id AND s.branch_id = bd.branch_id WHERE bd.clinic_id = :clinic_id AND bd.doctor_id = :doctor_id AND s.user_id = :user_id))
        RETURNING id, public_name, specialty, registration, verification_status, bio, consultation_duration_minutes, status, version, updated_at
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "doctor_id": doctor_id, "expected_version": payload.expected_version, **values}).mappings().one_or_none()
    if row is None:
        exists = db.execute(text("""
            SELECT version FROM doctor_profiles
            WHERE clinic_id = :clinic_id AND id = :doctor_id AND archived_at IS NULL
              AND (NOT EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id)
                   OR EXISTS (SELECT 1 FROM branch_doctors bd JOIN user_branch_scopes s ON s.clinic_id = bd.clinic_id AND s.branch_id = bd.branch_id WHERE bd.clinic_id = :clinic_id AND bd.doctor_id = :doctor_id AND s.user_id = :user_id))
        """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "doctor_id": doctor_id}).scalar_one_or_none()
        if exists is None:
            raise _error("NOT_FOUND", "Doctor not found.", status.HTTP_404_NOT_FOUND)
        raise _error("VERSION_CONFLICT", "The doctor changed before this update.", status.HTTP_409_CONFLICT)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="doctor.update", entity_type="doctor_profile", entity_id=row["id"], outcome="success", request_id=__import__("uuid").UUID(request.state.request_id), metadata={"fields": sorted(values)})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@catalog_router.post("/doctors/{doctor_id}/status")
def doctor_status(doctor_id: str, payload: CatalogStatusUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "doctor.manage", csrf_token)
    row = db.execute(text("""
        UPDATE doctor_profiles SET status = :status, archived_at = CASE WHEN :status = 'archived' THEN COALESCE(archived_at, now()) ELSE NULL END,
            version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :doctor_id
          AND (NOT EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id)
               OR EXISTS (SELECT 1 FROM branch_doctors bd JOIN user_branch_scopes s ON s.clinic_id = bd.clinic_id AND s.branch_id = bd.branch_id WHERE bd.clinic_id = :clinic_id AND bd.doctor_id = :doctor_id AND s.user_id = :user_id))
        RETURNING id, public_name, status, version, archived_at, updated_at
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "doctor_id": doctor_id, "status": payload.status}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Doctor not found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="doctor.status_change", entity_type="doctor_profile", entity_id=row["id"], outcome="success", request_id=__import__("uuid").UUID(request.state.request_id), metadata={"status": payload.status})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@catalog_router.get("/holidays")
def list_holidays(request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "schedule.read")
    cursor_values = decode_cursor(cursor, "holidays") if cursor else None
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    zero_uuid = "00000000-0000-0000-0000-000000000000"
    try:
        after_date = date.fromisoformat(cursor_values["holiday_date"]) if cursor_values else None
        after_time_set = int(cursor_values["starts_at_set"]) if cursor_values else None
        after_time = time.fromisoformat(cursor_values["starts_at"]) if cursor_values and cursor_values.get("starts_at") else time.min
        after_id = cursor_values["id"] if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT id, holiday_date, name, branch_id, starts_at, ends_at, created_at
        FROM clinic_holidays h
        WHERE h.clinic_id = :clinic_id
          AND (h.branch_id IS NULL
               OR NOT EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id)
               OR EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id AND s.branch_id = h.branch_id))
          AND (:after_date IS NULL OR (holiday_date, (starts_at IS NOT NULL)::int, COALESCE(starts_at, '00:00:00'::time), id) > (:after_date, :after_time_set, :after_time, CAST(:after_id AS uuid)))
        ORDER BY holiday_date, (starts_at IS NOT NULL)::int, COALESCE(starts_at, '00:00:00'::time), id
        LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "after_date": after_date, "after_time_set": after_time_set, "after_time": after_time, "after_id": after_id or zero_uuid, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_next and rows:
        last = rows[-1]
        next_cursor = encode_cursor("holidays", {"holiday_date": last["holiday_date"].isoformat(), "starts_at_set": "1" if last["starts_at"] is not None else "0", "starts_at": last["starts_at"].isoformat() if last["starts_at"] is not None else "", "id": str(last["id"])})
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@catalog_router.post("/holidays", status_code=status.HTTP_201_CREATED)
def create_holiday(payload: HolidayCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "schedule.manage", csrf_token, branch_id=payload.branch_id)
    try:
        row = db.execute(text("INSERT INTO clinic_holidays (clinic_id, holiday_date, name, branch_id, starts_at, ends_at) VALUES (:clinic_id, :holiday_date, :name, :branch_id, :starts_at, :ends_at) RETURNING id, holiday_date, name, branch_id, starts_at, ends_at, created_at"), {"clinic_id": session["clinic_id"], **payload.model_dump()}).mappings().one()
    except Exception as exc:
        db.rollback()
        if "uq_clinic_holidays_date" in str(exc):
            raise _error("DUPLICATE", "A holiday already exists on this date.", status.HTTP_409_CONFLICT) from exc
        raise
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@catalog_router.delete("/holidays/{holiday_id}")
def delete_holiday(holiday_id: str, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _session_or_401(db, session_token)
    if session["clinic_id"] is None:
        raise _error("FORBIDDEN", "A clinic context is required.", status.HTTP_403_FORBIDDEN)
    set_tenant_context(db, session["clinic_id"], session["user_id"])
    branch_id = db.execute(text("SELECT branch_id FROM clinic_holidays WHERE clinic_id = :clinic_id AND id = :id"), {"clinic_id": session["clinic_id"], "id": holiday_id}).scalar_one_or_none()
    if branch_id is None and db.execute(text("SELECT 1 FROM clinic_holidays WHERE clinic_id = :clinic_id AND id = :id"), {"clinic_id": session["clinic_id"], "id": holiday_id}).scalar_one_or_none() is None:
        raise _error("NOT_FOUND", "Holiday not found.", status.HTTP_404_NOT_FOUND)
    session = _write_authorized(db, request, session_token, "schedule.manage", csrf_token, branch_id=branch_id)
    deleted = db.execute(text("DELETE FROM clinic_holidays WHERE clinic_id = :clinic_id AND id = :id RETURNING id"), {"clinic_id": session["clinic_id"], "id": holiday_id}).scalar_one_or_none()
    if deleted is None:
        raise _error("NOT_FOUND", "Holiday not found.", status.HTTP_404_NOT_FOUND)
    db.commit()
    return {"data": {"id": deleted, "deleted": True}, "meta": {"request_id": request.state.request_id}}


@catalog_router.post("/branches/{branch_id}/rooms", status_code=status.HTTP_201_CREATED)
def create_room(branch_id: str, payload: RoomCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "branch.manage", csrf_token, branch_id=branch_id)
    try:
        row = db.execute(text("INSERT INTO rooms (clinic_id, branch_id, name) SELECT :clinic_id, id, :name FROM branches WHERE clinic_id = :clinic_id AND id = :branch_id AND archived_at IS NULL RETURNING id, branch_id, name, status, version, created_at, updated_at"), {"clinic_id": session["clinic_id"], "branch_id": branch_id, "name": payload.name.strip()}).mappings().one_or_none()
    except Exception as exc:
        db.rollback()
        raise _error("DUPLICATE", "A room with this name already exists.", status.HTTP_409_CONFLICT) from exc
    if row is None:
        raise _error("NOT_FOUND", "Branch not found.", status.HTTP_404_NOT_FOUND)
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@catalog_router.get("/branches/{branch_id}/rooms")
def list_rooms(branch_id: str, request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "branch.read", branch_id=branch_id)
    cursor_values = decode_cursor(cursor, "rooms") if cursor else None
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    try:
        after_name = cursor_values["name"] if cursor_values else None
        after_id = cursor_values["id"] if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT id, branch_id, name, status, version, created_at, updated_at
        FROM rooms
        WHERE clinic_id = :clinic_id AND branch_id = :branch_id AND archived_at IS NULL
          AND (:after_name IS NULL OR name > :after_name OR (name = :after_name AND id > :after_id))
        ORDER BY name, id
        LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "branch_id": branch_id, "after_name": after_name, "after_id": after_id, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor("rooms", {"name": rows[-1]["name"], "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@catalog_router.post("/branches/{branch_id}/resources", status_code=status.HTTP_201_CREATED)
def create_resource(branch_id: str, payload: ResourceCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "branch.manage", csrf_token, branch_id=branch_id)
    try:
        row = db.execute(text("INSERT INTO resources (clinic_id, branch_id, name, capacity) SELECT :clinic_id, id, :name, :capacity FROM branches WHERE clinic_id = :clinic_id AND id = :branch_id AND archived_at IS NULL RETURNING id, branch_id, name, capacity, status, version, created_at, updated_at"), {"clinic_id": session["clinic_id"], "branch_id": branch_id, "name": payload.name.strip(), "capacity": payload.capacity}).mappings().one_or_none()
    except Exception as exc:
        db.rollback()
        raise _error("DUPLICATE", "A resource with this name already exists.", status.HTTP_409_CONFLICT) from exc
    if row is None:
        raise _error("NOT_FOUND", "Branch not found.", status.HTTP_404_NOT_FOUND)
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@catalog_router.get("/branches/{branch_id}/resources")
def list_resources(branch_id: str, request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "branch.read", branch_id=branch_id)
    cursor_values = decode_cursor(cursor, "resources") if cursor else None
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    try:
        after_name = cursor_values["name"] if cursor_values else None
        after_id = cursor_values["id"] if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT id, branch_id, name, capacity, status, version, created_at, updated_at
        FROM resources
        WHERE clinic_id = :clinic_id AND branch_id = :branch_id AND archived_at IS NULL
          AND (:after_name IS NULL OR name > :after_name OR (name = :after_name AND id > :after_id))
        ORDER BY name, id
        LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "branch_id": branch_id, "after_name": after_name, "after_id": after_id, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor("resources", {"name": rows[-1]["name"], "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@catalog_router.patch("/branches/{branch_id}/rooms/{room_id}")
def update_room(branch_id: str, room_id: str, payload: RoomUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "branch.manage", csrf_token, branch_id=branch_id)
    row = db.execute(text("""
        UPDATE rooms SET name = :name, version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND branch_id = :branch_id AND id = :room_id
          AND archived_at IS NULL AND version = :expected_version
        RETURNING id, branch_id, name, status, version, updated_at
    """), {"clinic_id": session["clinic_id"], "branch_id": branch_id, "room_id": room_id, "name": payload.name.strip(), "expected_version": payload.expected_version}).mappings().one_or_none()
    if row is None:
        exists = db.execute(text("SELECT version FROM rooms WHERE clinic_id = :clinic_id AND branch_id = :branch_id AND id = :room_id AND archived_at IS NULL"), {"clinic_id": session["clinic_id"], "branch_id": branch_id, "room_id": room_id}).scalar_one_or_none()
        if exists is None:
            raise _error("NOT_FOUND", "Room not found.", status.HTTP_404_NOT_FOUND)
        raise _error("VERSION_CONFLICT", "The room changed before this update.", status.HTTP_409_CONFLICT)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="room.update", entity_type="room", entity_id=row["id"], outcome="success", request_id=__import__("uuid").UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@catalog_router.patch("/branches/{branch_id}/resources/{resource_id}")
def update_resource(branch_id: str, resource_id: str, payload: ResourceUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "branch.manage", csrf_token, branch_id=branch_id)
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    assignments = ", ".join(f"{field} = :{field}" for field in values)
    row = db.execute(text(f"""
        UPDATE resources SET {assignments}, version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND branch_id = :branch_id AND id = :resource_id
          AND archived_at IS NULL AND version = :expected_version
        RETURNING id, branch_id, name, capacity, status, version, updated_at
    """), {"clinic_id": session["clinic_id"], "branch_id": branch_id, "resource_id": resource_id, "expected_version": payload.expected_version, **values}).mappings().one_or_none()
    if row is None:
        exists = db.execute(text("SELECT version FROM resources WHERE clinic_id = :clinic_id AND branch_id = :branch_id AND id = :resource_id AND archived_at IS NULL"), {"clinic_id": session["clinic_id"], "branch_id": branch_id, "resource_id": resource_id}).scalar_one_or_none()
        if exists is None:
            raise _error("NOT_FOUND", "Resource not found.", status.HTTP_404_NOT_FOUND)
        raise _error("VERSION_CONFLICT", "The resource changed before this update.", status.HTTP_409_CONFLICT)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="resource.update", entity_type="resource", entity_id=row["id"], outcome="success", request_id=__import__("uuid").UUID(request.state.request_id), metadata={"fields": sorted(values)})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@catalog_router.post("/branches/{branch_id}/rooms/{room_id}/status")
def room_status(branch_id: str, room_id: str, payload: CatalogStatusUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "branch.manage", csrf_token, branch_id=branch_id)
    row = db.execute(text("UPDATE rooms SET status = :status, archived_at = CASE WHEN :status = 'archived' THEN COALESCE(archived_at, now()) ELSE NULL END, version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND branch_id = :branch_id AND id = :room_id RETURNING id, branch_id, status, version, archived_at, updated_at"), {"clinic_id": session["clinic_id"], "branch_id": branch_id, "room_id": room_id, "status": payload.status}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Room not found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="room.status_change", entity_type="room", entity_id=row["id"], outcome="success", request_id=__import__("uuid").UUID(request.state.request_id), metadata={"status": payload.status})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@catalog_router.post("/branches/{branch_id}/resources/{resource_id}/status")
def resource_status(branch_id: str, resource_id: str, payload: CatalogStatusUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "branch.manage", csrf_token, branch_id=branch_id)
    row = db.execute(text("UPDATE resources SET status = :status, archived_at = CASE WHEN :status = 'archived' THEN COALESCE(archived_at, now()) ELSE NULL END, version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND branch_id = :branch_id AND id = :resource_id RETURNING id, branch_id, status, version, archived_at, updated_at"), {"clinic_id": session["clinic_id"], "branch_id": branch_id, "resource_id": resource_id, "status": payload.status}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Resource not found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="resource.status_change", entity_type="resource", entity_id=row["id"], outcome="success", request_id=__import__("uuid").UUID(request.state.request_id), metadata={"status": payload.status})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@catalog_router.post("/doctors/{doctor_id}/services/{service_id}", status_code=status.HTTP_201_CREATED)
def assign_doctor_service(doctor_id: str, service_id: str, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "doctor.manage", csrf_token)
    visible_doctor = db.execute(text("""
        SELECT 1
        FROM doctor_profiles d
        WHERE d.clinic_id = :clinic_id
          AND d.id = :doctor_id
          AND d.archived_at IS NULL
          AND (
            NOT EXISTS (SELECT 1 FROM user_branch_scopes s WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id)
            OR EXISTS (
                SELECT 1
                FROM branch_doctors bd
                JOIN user_branch_scopes s ON s.clinic_id = bd.clinic_id AND s.branch_id = bd.branch_id
                WHERE bd.clinic_id = :clinic_id AND bd.doctor_id = :doctor_id AND s.user_id = :user_id
            )
          )
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "doctor_id": doctor_id}).scalar_one_or_none()
    service_exists = db.execute(text("SELECT 1 FROM services WHERE clinic_id = :clinic_id AND id = :service_id AND archived_at IS NULL"), {"clinic_id": session["clinic_id"], "service_id": service_id}).scalar_one_or_none()
    if visible_doctor is None or service_exists is None:
        raise _error("NOT_FOUND", "Doctor or service is not available in your clinic scope.", status.HTTP_404_NOT_FOUND)
    try:
        db.execute(text("INSERT INTO doctor_services (clinic_id, doctor_id, service_id) VALUES (:clinic_id, :doctor_id, :service_id)"), {"clinic_id": session["clinic_id"], "doctor_id": doctor_id, "service_id": service_id})
    except Exception as exc:
        db.rollback()
        raise _error("NOT_FOUND", "Doctor or service not found, or assignment already exists.", status.HTTP_409_CONFLICT) from exc
    db.commit()
    return {"data": {"doctor_id": doctor_id, "service_id": service_id, "assigned": True}, "meta": {"request_id": request.state.request_id}}


@catalog_router.post("/branches/{branch_id}/doctors/{doctor_id}", status_code=status.HTTP_201_CREATED)
def assign_branch_doctor(branch_id: str, doctor_id: str, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "branch.manage", csrf_token, branch_id=branch_id)
    try:
        db.execute(text("INSERT INTO branch_doctors (clinic_id, branch_id, doctor_id) VALUES (:clinic_id, :branch_id, :doctor_id)"), {"clinic_id": session["clinic_id"], "branch_id": branch_id, "doctor_id": doctor_id})
    except Exception as exc:
        db.rollback()
        raise _error("NOT_FOUND", "Branch or doctor not found, or assignment already exists.", status.HTTP_409_CONFLICT) from exc
    db.commit()
    return {"data": {"branch_id": branch_id, "doctor_id": doctor_id, "assigned": True}, "meta": {"request_id": request.state.request_id}}


@catalog_router.get("/branches/{branch_id}/doctors")
def list_branch_doctors(branch_id: str, request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "branch.read", branch_id=branch_id)
    cursor_values = decode_cursor(cursor, "branch-doctors") if cursor else None
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    try:
        after_name = cursor_values["name"] if cursor_values else None
        after_id = cursor_values["id"] if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT d.id, d.public_name, d.specialty, d.registration, d.verification_status,
               d.bio, d.consultation_duration_minutes, d.status
        FROM branch_doctors bd
        JOIN doctor_profiles d ON d.clinic_id = bd.clinic_id AND d.id = bd.doctor_id
        WHERE bd.clinic_id = :clinic_id AND bd.branch_id = :branch_id AND d.archived_at IS NULL
          AND (:after_name IS NULL OR d.public_name > :after_name OR (d.public_name = :after_name AND d.id > :after_id))
        ORDER BY d.public_name, d.id
        LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "branch_id": branch_id, "after_name": after_name, "after_id": after_id, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor("branch-doctors", {"name": rows[-1]["public_name"], "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@catalog_router.delete("/branches/{branch_id}/doctors/{doctor_id}")
def unassign_branch_doctor(branch_id: str, doctor_id: str, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "branch.manage", csrf_token, branch_id=branch_id)
    deleted = db.execute(text("DELETE FROM branch_doctors WHERE clinic_id = :clinic_id AND branch_id = :branch_id AND doctor_id = :doctor_id RETURNING doctor_id"), {"clinic_id": session["clinic_id"], "branch_id": branch_id, "doctor_id": doctor_id}).scalar_one_or_none()
    if deleted is None:
        raise _error("NOT_FOUND", "Branch-doctor assignment not found.", status.HTTP_404_NOT_FOUND)
    db.commit()
    return {"data": {"branch_id": branch_id, "doctor_id": deleted, "assigned": False}, "meta": {"request_id": request.state.request_id}}


@catalog_router.post("/branches/{branch_id}/services/{service_id}", status_code=status.HTTP_201_CREATED)
def assign_branch_service(branch_id: str, service_id: str, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "branch.manage", csrf_token, branch_id=branch_id)
    try:
        db.execute(text("INSERT INTO branch_services (clinic_id, branch_id, service_id) VALUES (:clinic_id, :branch_id, :service_id)"), {"clinic_id": session["clinic_id"], "branch_id": branch_id, "service_id": service_id})
    except Exception as exc:
        db.rollback()
        raise _error("CONFLICT", "Branch or service not found, or assignment already exists.", status.HTTP_409_CONFLICT) from exc
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="branch.service_assign", entity_type="branch_service", entity_id=None, outcome="success", request_id=__import__("uuid").UUID(request.state.request_id), metadata={"branch_id": str(branch_id), "service_id": str(service_id)})
    db.commit()
    return {"data": {"branch_id": branch_id, "service_id": service_id, "assigned": True}, "meta": {"request_id": request.state.request_id}}


@catalog_router.get("/branches/{branch_id}/services")
def list_branch_services(branch_id: str, request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "branch.read", branch_id=branch_id)
    cursor_values = decode_cursor(cursor, "branch-services") if cursor else None
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    try:
        after_name = cursor_values["name"] if cursor_values else None
        after_id = cursor_values["id"] if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT s.id, s.name, s.category, s.duration_minutes, s.buffer_before_minutes,
               s.buffer_after_minutes, s.price_mode, s.amount_minor, s.currency,
               s.approval_mode, s.visibility, s.status, s.version
        FROM branch_services bs
        JOIN services s ON s.clinic_id = bs.clinic_id AND s.id = bs.service_id
        WHERE bs.clinic_id = :clinic_id AND bs.branch_id = :branch_id AND s.archived_at IS NULL
          AND (:after_name IS NULL OR s.name > :after_name OR (s.name = :after_name AND s.id > :after_id))
        ORDER BY s.name, s.id
        LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "branch_id": branch_id, "after_name": after_name, "after_id": after_id, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor("branch-services", {"name": rows[-1]["name"], "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@catalog_router.delete("/branches/{branch_id}/services/{service_id}")
def unassign_branch_service(branch_id: str, service_id: str, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "branch.manage", csrf_token, branch_id=branch_id)
    deleted = db.execute(text("DELETE FROM branch_services WHERE clinic_id = :clinic_id AND branch_id = :branch_id AND service_id = :service_id RETURNING service_id"), {"clinic_id": session["clinic_id"], "branch_id": branch_id, "service_id": service_id}).scalar_one_or_none()
    if deleted is None:
        raise _error("NOT_FOUND", "Branch-service assignment not found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="branch.service_unassign", entity_type="branch_service", entity_id=None, outcome="success", request_id=__import__("uuid").UUID(request.state.request_id), metadata={"branch_id": str(branch_id), "service_id": str(service_id)})
    db.commit()
    return {"data": {"branch_id": branch_id, "service_id": deleted, "assigned": False}, "meta": {"request_id": request.state.request_id}}


@router.get("")
def list_services(request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "service.read")
    cursor_values = decode_cursor(cursor, "services") if cursor else None
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    try:
        after_name = cursor_values["name"] if cursor_values else None
        after_id = cursor_values["id"] if cursor_values else None
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST) from exc
    rows = db.execute(text("""
        SELECT id, name, category, short_description, duration_minutes, buffer_before_minutes,
               buffer_after_minutes, price_mode, amount_minor, currency, approval_mode, visibility,
               status, version, created_at, updated_at
        FROM services
        WHERE clinic_id = :clinic_id AND archived_at IS NULL
          AND (:after_name IS NULL OR name > :after_name OR (name = :after_name AND id > :after_id))
        ORDER BY name, id
        LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "after_name": after_name, "after_id": after_id, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor("services", {"name": rows[-1]["name"], "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_service(payload: ServiceCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    _validate_origin(request)
    session = _authorized(db, session_token, "service.manage")
    if not csrf_token:
        raise _error("CSRF_REQUIRED", "A CSRF token is required.", status.HTTP_403_FORBIDDEN)
    try:
        verify_csrf(session, csrf_token)
    except SessionError as exc:
        raise _error("CSRF_INVALID", "The CSRF token is invalid.", status.HTTP_403_FORBIDDEN) from exc
    if payload.price_mode == "exact" and (payload.amount_minor is None or payload.currency is None):
        raise _error("INVALID_INPUT", "Exact prices require amount_minor and currency.", status.HTTP_400_BAD_REQUEST)
    row = db.execute(text("""
        INSERT INTO services
          (clinic_id, name, category, short_description, full_description, duration_minutes,
           buffer_before_minutes, buffer_after_minutes, price_mode, amount_minor, currency,
           approval_mode, visibility)
        VALUES (:clinic_id, :name, :category, :short_description, :full_description, :duration_minutes,
                :buffer_before_minutes, :buffer_after_minutes, :price_mode, :amount_minor, :currency,
                :approval_mode, :visibility)
        RETURNING id, name, category, duration_minutes, buffer_before_minutes, buffer_after_minutes,
                  price_mode, amount_minor, currency, approval_mode, visibility, status, version
    """), {"clinic_id": session["clinic_id"], **payload.model_dump()}).mappings().one()
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.patch("/{service_id}")
def update_service(service_id: str, payload: ServiceUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    _validate_origin(request)
    session = _authorized(db, session_token, "service.manage")
    if not csrf_token:
        raise _error("CSRF_REQUIRED", "A CSRF token is required.", status.HTTP_403_FORBIDDEN)
    try:
        verify_csrf(session, csrf_token)
    except SessionError as exc:
        raise _error("CSRF_INVALID", "The CSRF token is invalid.", status.HTTP_403_FORBIDDEN) from exc
    current = db.execute(text("SELECT name, category, short_description, full_description, duration_minutes, buffer_before_minutes, buffer_after_minutes, price_mode, amount_minor, currency, approval_mode, visibility, version FROM services WHERE clinic_id = :clinic_id AND id = :service_id AND archived_at IS NULL FOR UPDATE"), {"clinic_id": session["clinic_id"], "service_id": service_id}).mappings().one_or_none()
    if current is None:
        raise _error("NOT_FOUND", "Service not found.", status.HTTP_404_NOT_FOUND)
    if current["version"] != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The service changed before this update.", status.HTTP_409_CONFLICT)
    values = dict(current)
    values.update(payload.model_dump(exclude={"expected_version"}, exclude_unset=True))
    if values["price_mode"] == "exact" and (values["amount_minor"] is None or values["currency"] is None):
        raise _error("INVALID_INPUT", "Exact prices require amount_minor and currency.", status.HTTP_400_BAD_REQUEST)
    if values["name"] is None:
        raise _error("INVALID_INPUT", "Service name cannot be cleared.", status.HTTP_400_BAD_REQUEST)
    values["name"] = values["name"].strip()
    fields = ("name", "category", "short_description", "full_description", "duration_minutes", "buffer_before_minutes", "buffer_after_minutes", "price_mode", "amount_minor", "currency", "approval_mode", "visibility")
    row = db.execute(text(f"""
        UPDATE services SET {', '.join(f'{field} = :{field}' for field in fields)}, version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :service_id AND version = :expected_version
        RETURNING id, name, category, short_description, duration_minutes, buffer_before_minutes, buffer_after_minutes,
                  price_mode, amount_minor, currency, approval_mode, visibility, status, version, updated_at
    """), {"clinic_id": session["clinic_id"], "service_id": service_id, "expected_version": payload.expected_version, **{field: values[field] for field in fields}}).mappings().one_or_none()
    if row is None:
        raise _error("VERSION_CONFLICT", "The service changed before this update.", status.HTTP_409_CONFLICT)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="service.update", entity_type="service", entity_id=row["id"], outcome="success", request_id=__import__("uuid").UUID(request.state.request_id), metadata={"fields": sorted(payload.model_dump(exclude={"expected_version"}, exclude_unset=True))})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.post("/{service_id}/status")
def service_status(service_id: str, payload: CatalogStatusUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    _validate_origin(request)
    session = _authorized(db, session_token, "service.manage")
    if not csrf_token:
        raise _error("CSRF_REQUIRED", "A CSRF token is required.", status.HTTP_403_FORBIDDEN)
    try:
        verify_csrf(session, csrf_token)
    except SessionError as exc:
        raise _error("CSRF_INVALID", "The CSRF token is invalid.", status.HTTP_403_FORBIDDEN) from exc
    row = db.execute(text("""
        UPDATE services SET status = :status, archived_at = CASE WHEN :status = 'archived' THEN COALESCE(archived_at, now()) ELSE NULL END,
            version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :service_id
        RETURNING id, name, status, version, archived_at, updated_at
    """), {"clinic_id": session["clinic_id"], "service_id": service_id, "status": payload.status}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Service not found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="service.status_change", entity_type="service", entity_id=row["id"], outcome="success", request_id=__import__("uuid").UUID(request.state.request_id), metadata={"status": payload.status})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}

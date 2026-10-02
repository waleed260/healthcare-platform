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
from app.modules.clinical.schemas import PrescriptionCreate, PrescriptionStatusUpdate, TreatmentPlanCreate, TreatmentPlanItemCreate, TreatmentPlanItemUpdate, TreatmentPlanUpdate
from app.modules.identity.routes import _error, _session_or_401, _validate_origin
from app.modules.identity.service import SessionError, verify_csrf

router = APIRouter(prefix="/api/v1/treatment-plans", tags=["clinical"])
prescription_router = APIRouter(prefix="/api/v1/patients", tags=["clinical"])


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
def plan_list(patient_id: UUID | None = None, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "clinical.read")
    cursor_values = decode_cursor(cursor, "treatment-plans") if cursor else None
    rows = db.execute(text("""
        SELECT id, patient_id, created_by_user_id, title, diagnosis, status, starts_on, ends_on, version, created_at, updated_at
        FROM treatment_plans
        WHERE clinic_id = :clinic_id AND archived_at IS NULL
          AND (:patient_id IS NULL OR patient_id = :patient_id)
          AND (:after_created_at IS NULL OR (created_at, id) < (CAST(:after_created_at AS timestamptz), CAST(:after_id AS uuid)))
        ORDER BY created_at DESC, id DESC LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "after_created_at": cursor_values.get("created_at") if cursor_values else None, "after_id": cursor_values.get("id") if cursor_values else None, "page_size": limit + 1}).mappings().all()
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = encode_cursor("treatment-plans", {"created_at": last["created_at"].isoformat(), "id": str(last["id"])})
        rows = rows[:limit]
    return {"data": [dict(row) for row in rows], "meta": {"next_cursor": next_cursor}}


@router.post("", status_code=status.HTTP_201_CREATED)
def plan_create(payload: TreatmentPlanCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "clinical.manage", csrf_token)
    row = db.execute(text("""
        INSERT INTO treatment_plans (clinic_id, patient_id, created_by_user_id, title, diagnosis, starts_on, ends_on)
        VALUES (:clinic_id, :patient_id, :user_id, :title, :diagnosis, :starts_on, :ends_on)
        RETURNING id, patient_id, created_by_user_id, title, diagnosis, status, starts_on, ends_on, version, created_at, updated_at
    """), {"clinic_id": session["clinic_id"], "patient_id": payload.patient_id, "user_id": session["user_id"], **payload.model_dump(exclude={"patient_id"})}).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="treatment_plan.create", entity_type="treatment_plan", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.patch("/{plan_id}")
def plan_update(plan_id: UUID, payload: TreatmentPlanUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "clinical.manage", csrf_token)
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    if not values:
        raise _error("INVALID_INPUT", "At least one treatment plan field must be provided.", status.HTTP_400_BAD_REQUEST)
    setters = ", ".join(f"{field} = :{field}" for field in values)
    row = db.execute(text(f"UPDATE treatment_plans SET {setters}, version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :id AND version = :expected_version AND archived_at IS NULL RETURNING id, patient_id, title, diagnosis, status, starts_on, ends_on, version, updated_at"), {"clinic_id": session["clinic_id"], "id": plan_id, "expected_version": payload.expected_version, **values}).mappings().one_or_none()
    if row is None:
        raise _error("VERSION_CONFLICT", "The treatment plan changed before this update.", status.HTTP_409_CONFLICT)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="treatment_plan.update", entity_type="treatment_plan", entity_id=plan_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.get("/{plan_id}/items")
def item_list(plan_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "clinical.read")
    rows = db.execute(text("SELECT id, plan_id, service_id, appointment_id, assigned_doctor_id, title, instructions, status, sort_order, due_on, completed_at, version, created_at, updated_at FROM treatment_plan_items WHERE clinic_id = :clinic_id AND plan_id = :plan_id ORDER BY sort_order, created_at, id"), {"clinic_id": session["clinic_id"], "plan_id": plan_id}).mappings().all()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.post("/{plan_id}/items", status_code=status.HTTP_201_CREATED)
def item_create(plan_id: UUID, payload: TreatmentPlanItemCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "clinical.manage", csrf_token)
    row = db.execute(text("""
        INSERT INTO treatment_plan_items (clinic_id, plan_id, service_id, appointment_id, assigned_doctor_id, title, instructions, due_on, sort_order)
        VALUES (:clinic_id, :plan_id, :service_id, :appointment_id, :assigned_doctor_id, :title, :instructions, :due_on, :sort_order)
        RETURNING id, plan_id, service_id, appointment_id, assigned_doctor_id, title, instructions, status, sort_order, due_on, completed_at, version, created_at, updated_at
    """), {"clinic_id": session["clinic_id"], "plan_id": plan_id, **payload.model_dump()}).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="treatment_plan.item.create", entity_type="treatment_plan_item", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.patch("/{plan_id}/items/{item_id}")
def item_update(plan_id: UUID, item_id: UUID, payload: TreatmentPlanItemUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "clinical.manage", csrf_token)
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    if not values:
        raise _error("INVALID_INPUT", "At least one treatment item field must be provided.", status.HTTP_400_BAD_REQUEST)
    setters = ", ".join(f"{field} = :{field}" for field in values)
    completed = "completed_at = CASE WHEN :status = 'completed' THEN COALESCE(completed_at, now()) WHEN :status IS NOT NULL THEN NULL ELSE completed_at END"
    row = db.execute(text(f"UPDATE treatment_plan_items SET {setters}, {completed}, version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND plan_id = :plan_id AND id = :id AND version = :expected_version RETURNING id, plan_id, service_id, appointment_id, assigned_doctor_id, title, instructions, status, sort_order, due_on, completed_at, version, updated_at"), {"clinic_id": session["clinic_id"], "plan_id": plan_id, "id": item_id, "expected_version": payload.expected_version, "status": values.get("status"), **values}).mappings().one_or_none()
    if row is None:
        raise _error("VERSION_CONFLICT", "The treatment item changed before this update.", status.HTTP_409_CONFLICT)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="treatment_plan.item.update", entity_type="treatment_plan_item", entity_id=item_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@prescription_router.get("/{patient_id}/prescriptions")
def prescription_list(patient_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "clinical.read")
    rows = db.execute(text("""
        SELECT id, patient_id, appointment_id, prescribed_by_user_id, medication_name, dosage, frequency,
               duration, instructions, status, version, prescribed_at, updated_at
        FROM prescriptions WHERE clinic_id = :clinic_id AND patient_id = :patient_id
        ORDER BY prescribed_at DESC, id DESC
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id}).mappings().all()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@prescription_router.post("/{patient_id}/prescriptions", status_code=status.HTTP_201_CREATED)
def prescription_create(patient_id: UUID, payload: PrescriptionCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "clinical.manage", csrf_token)
    patient_exists = db.execute(text("SELECT 1 FROM patients WHERE clinic_id = :clinic_id AND id = :patient_id AND archived_at IS NULL"), {"clinic_id": session["clinic_id"], "patient_id": patient_id}).scalar_one_or_none()
    if patient_exists is None:
        raise _error("NOT_FOUND", "Patient not found.", status.HTTP_404_NOT_FOUND)
    if payload.appointment_id is not None:
        appointment_ok = db.execute(text("SELECT 1 FROM appointments WHERE clinic_id = :clinic_id AND id = :appointment_id AND patient_id = :patient_id AND archived_at IS NULL"), {"clinic_id": session["clinic_id"], "appointment_id": payload.appointment_id, "patient_id": patient_id}).scalar_one_or_none()
        if appointment_ok is None:
            raise _error("NOT_FOUND", "The appointment is not associated with this patient.", status.HTTP_404_NOT_FOUND)
    row = db.execute(text("""
        INSERT INTO prescriptions (clinic_id, patient_id, appointment_id, prescribed_by_user_id, medication_name, dosage, frequency, duration, instructions)
        VALUES (:clinic_id, :patient_id, :appointment_id, :user_id, :medication_name, :dosage, :frequency, :duration, :instructions)
        RETURNING id, patient_id, appointment_id, prescribed_by_user_id, medication_name, dosage, frequency, duration, instructions, status, version, prescribed_at, updated_at
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "user_id": session["user_id"], **payload.model_dump()}).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="prescription.create", entity_type="prescription", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@prescription_router.patch("/{patient_id}/prescriptions/{prescription_id}/status")
def prescription_status(patient_id: UUID, prescription_id: UUID, payload: PrescriptionStatusUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "clinical.manage", csrf_token)
    row = db.execute(text("""
        UPDATE prescriptions SET status = :status, version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND patient_id = :patient_id AND id = :id AND version = :expected_version
        RETURNING id, patient_id, medication_name, status, version, updated_at
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "id": prescription_id, "status": payload.status, "expected_version": payload.expected_version}).mappings().one_or_none()
    if row is None:
        raise _error("VERSION_CONFLICT", "The prescription changed before this update.", status.HTTP_409_CONFLICT)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="prescription.status", entity_type="prescription", entity_id=prescription_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"status": payload.status})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}

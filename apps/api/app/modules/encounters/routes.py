from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import decode_cursor, encode_cursor
from app.db.session import get_db
from app.db.tenant import set_tenant_context
from app.modules.audit.service import record_event
from app.modules.authorization.service import ForbiddenError, require_permission
from app.modules.encounters.schemas import EncounterCreate, EncounterStatusUpdate, EncounterUpdate
from app.modules.identity.routes import _error, _session_or_401, _validate_origin
from app.modules.identity.service import SessionError, verify_csrf

router = APIRouter(prefix="/api/v1/encounters", tags=["encounters"])


def _authorized(db: Session, session_token: str | None, permission: str) -> dict:
    session = _session_or_401(db, session_token)
    if session["clinic_id"] is None:
        raise _error("FORBIDDEN", "A clinic context is required.", status.HTTP_403_FORBIDDEN)
    set_tenant_context(db, session["clinic_id"], session["user_id"])
    try:
        require_permission(db, session["user_id"], session["clinic_id"], permission)
    except ForbiddenError as exc:
        raise _error("FORBIDDEN", "You do not have permission.", status.HTTP_403_FORBIDDEN) from exc
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
def encounter_list(
    patient_id: UUID | None = Query(default=None),
    doctor_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status", max_length=20),
    cursor: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=50, ge=1, le=100),
    request: Request = None,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
) -> dict:
    session = _authorized(db, session_token, "clinical.read")
    cursor_values = decode_cursor(cursor, "encounters") if cursor else None
    rows = db.execute(text("""
        SELECT e.id, e.patient_id, p.full_name AS patient_name, e.appointment_id,
               e.doctor_id, d.public_name AS doctor_name, e.branch_id,
               e.encounter_type, e.status, e.chief_complaint,
               e.diagnosis, e.finalized_at, e.created_at, e.updated_at, e.version
        FROM encounter_forms e
        JOIN patients p ON p.clinic_id = e.clinic_id AND p.id = e.patient_id
        JOIN doctor_profiles d ON d.clinic_id = e.clinic_id AND d.id = e.doctor_id
        WHERE e.clinic_id = :clinic_id AND e.archived_at IS NULL
          AND (:patient_id IS NULL OR e.patient_id = :patient_id)
          AND (:doctor_id IS NULL OR e.doctor_id = :doctor_id)
          AND (:status IS NULL OR e.status = :status)
          AND (:after_created IS NULL OR (e.created_at, e.id) < (CAST(:after_created AS timestamptz), CAST(:after_id AS uuid)))
        ORDER BY e.created_at DESC, e.id DESC
        LIMIT :page_size
    """), {
        "clinic_id": session["clinic_id"],
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "status": status_filter,
        "after_created": cursor_values.get("created_at") if cursor_values else None,
        "after_id": cursor_values.get("id") if cursor_values else None,
        "page_size": limit + 1,
    }).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor("encounters", {"created_at": rows[-1]["created_at"].isoformat(), "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@router.get("/{encounter_id}")
def encounter_detail(
    encounter_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
) -> dict:
    session = _authorized(db, session_token, "clinical.read")
    row = db.execute(text("""
        SELECT e.*, p.full_name AS patient_name, p.mrn,
               d.public_name AS doctor_name, d.specialty AS doctor_specialty,
               b.name AS branch_name
        FROM encounter_forms e
        JOIN patients p ON p.clinic_id = e.clinic_id AND p.id = e.patient_id
        JOIN doctor_profiles d ON d.clinic_id = e.clinic_id AND d.id = e.doctor_id
        LEFT JOIN branches b ON b.clinic_id = e.clinic_id AND b.id = e.branch_id
        WHERE e.clinic_id = :clinic_id AND e.id = :encounter_id AND e.archived_at IS NULL
    """), {"clinic_id": session["clinic_id"], "encounter_id": encounter_id}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Encounter not found.", status.HTTP_404_NOT_FOUND)
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.post("", status_code=status.HTTP_201_CREATED)
def encounter_create(
    payload: EncounterCreate,
    request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    session = _write_authorized(db, request, session_token, "clinical.manage", csrf_token)
    patient = db.execute(text("SELECT 1 FROM patients WHERE clinic_id = :clinic_id AND id = :patient_id AND archived_at IS NULL"), {"clinic_id": session["clinic_id"], "patient_id": payload.patient_id}).scalar_one_or_none()
    if patient is None:
        raise _error("NOT_FOUND", "Patient not found.", status.HTTP_404_NOT_FOUND)
    doctor = db.execute(text("SELECT 1 FROM doctor_profiles WHERE clinic_id = :clinic_id AND id = :doctor_id AND archived_at IS NULL"), {"clinic_id": session["clinic_id"], "doctor_id": payload.doctor_id}).scalar_one_or_none()
    if doctor is None:
        raise _error("NOT_FOUND", "Doctor not found.", status.HTTP_404_NOT_FOUND)
    row = db.execute(text("""
        INSERT INTO encounter_forms (clinic_id, patient_id, appointment_id, doctor_id, branch_id,
                                     encounter_type, chief_complaint, arrival_vitals, created_by)
        VALUES (:clinic_id, :patient_id, :appointment_id, :doctor_id, :branch_id,
                :encounter_type, :chief_complaint, CAST(:arrival_vitals AS jsonb), :created_by)
        RETURNING id, patient_id, appointment_id, doctor_id, branch_id, encounter_type,
                  chief_complaint, arrival_vitals, status, version, created_at
    """), {
        "clinic_id": session["clinic_id"],
        "patient_id": payload.patient_id,
        "appointment_id": payload.appointment_id,
        "doctor_id": payload.doctor_id,
        "branch_id": payload.branch_id,
        "encounter_type": payload.encounter_type,
        "chief_complaint": payload.chief_complaint,
        "arrival_vitals": json.dumps(payload.arrival_vitals.model_dump()) if payload.arrival_vitals else None,
        "created_by": session["user_id"],
    }).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="encounter.create", entity_type="encounter_form", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.patch("/{encounter_id}")
def encounter_update(
    encounter_id: UUID,
    payload: EncounterUpdate,
    request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    session = _write_authorized(db, request, session_token, "clinical.manage", csrf_token)
    current = db.execute(text("SELECT version, status FROM encounter_forms WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL FOR UPDATE"), {"clinic_id": session["clinic_id"], "id": encounter_id}).mappings().one_or_none()
    if current is None:
        raise _error("NOT_FOUND", "Encounter not found.", status.HTTP_404_NOT_FOUND)
    if current["status"] == "finalized":
        raise _error("FORBIDDEN", "A finalized encounter cannot be edited.", status.HTTP_403_FORBIDDEN)
    if current["version"] != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The encounter changed before this update.", status.HTTP_409_CONFLICT)
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    if not values:
        raise _error("INVALID_INPUT", "At least one field is required.", status.HTTP_400_BAD_REQUEST)
    updates = []
    params: dict = {"clinic_id": session["clinic_id"], "id": encounter_id}
    for field, val in values.items():
        if field in ("medications", "arrival_vitals", "discharge_vitals"):
            if val is not None:
                if field == "medications":
                    val = [m.model_dump() if hasattr(m, "model_dump") else m for m in val]
                else:
                    val = val.model_dump() if hasattr(val, "model_dump") else val
            updates.append(f"{field} = CAST(:{field} AS jsonb)")
            params[field] = json.dumps(val) if val is not None else None
        else:
            updates.append(f"{field} = :{field}")
            params[field] = val
    row = db.execute(text(f"""
        UPDATE encounter_forms SET {', '.join(updates)}, version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :id
        RETURNING id, patient_id, doctor_id, encounter_type, status,
                  chief_complaint, history_present_illness, examination_findings,
                  diagnosis, investigations, treatment_plan, medications,
                  procedures_performed, follow_up_instructions, follow_up_date,
                  arrival_vitals, discharge_vitals, discharge_notes, internal_notes,
                  version, updated_at
    """), params).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="encounter.update", entity_type="encounter_form", entity_id=encounter_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"fields": sorted(values.keys())})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.post("/{encounter_id}/status")
def encounter_status_update(
    encounter_id: UUID,
    payload: EncounterStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    session = _write_authorized(db, request, session_token, "clinical.manage", csrf_token)
    current = db.execute(text("SELECT version, status FROM encounter_forms WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL FOR UPDATE"), {"clinic_id": session["clinic_id"], "id": encounter_id}).mappings().one_or_none()
    if current is None:
        raise _error("NOT_FOUND", "Encounter not found.", status.HTTP_404_NOT_FOUND)
    if current["version"] != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The encounter changed before this update.", status.HTTP_409_CONFLICT)
    if current["status"] == "finalized" and payload.status != "finalized":
        raise _error("FORBIDDEN", "A finalized encounter cannot be reverted.", status.HTTP_403_FORBIDDEN)
    finalize_clause = ", finalized_at = now(), finalized_by = :actor" if payload.status == "finalized" and current["status"] != "finalized" else ""
    row = db.execute(text(f"""
        UPDATE encounter_forms SET status = :status{finalize_clause}, version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :id
        RETURNING id, status, finalized_at, finalized_by, version, updated_at
    """), {"clinic_id": session["clinic_id"], "id": encounter_id, "status": payload.status, "actor": session["user_id"]}).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="encounter.status", entity_type="encounter_form", entity_id=encounter_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"status": payload.status})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.delete("/{encounter_id}")
def encounter_archive(
    encounter_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    session = _write_authorized(db, request, session_token, "clinical.manage", csrf_token)
    current = db.execute(text("SELECT status FROM encounter_forms WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL"), {"clinic_id": session["clinic_id"], "id": encounter_id}).mappings().one_or_none()
    if current is None:
        raise _error("NOT_FOUND", "Encounter not found.", status.HTTP_404_NOT_FOUND)
    if current["status"] == "finalized":
        raise _error("FORBIDDEN", "A finalized encounter cannot be deleted.", status.HTTP_403_FORBIDDEN)
    db.execute(text("UPDATE encounter_forms SET archived_at = now() WHERE clinic_id = :clinic_id AND id = :id"), {"clinic_id": session["clinic_id"], "id": encounter_id})
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="encounter.archive", entity_type="encounter_form", entity_id=encounter_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": {"id": str(encounter_id)}, "meta": {"request_id": request.state.request_id}}

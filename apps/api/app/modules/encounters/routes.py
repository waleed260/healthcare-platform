from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import decode_cursor, encode_cursor
from app.db.session import get_db
from app.db.tenant import set_tenant_context
from app.modules.audit.service import record_event
from app.modules.authorization.service import ForbiddenError, require_permission
from app.modules.encounters.schemas import (
    EncounterAmendment,
    EncounterCreate,
    EncounterDischarge,
    EncounterStatusUpdate,
    EncounterUpdate,
)
from app.modules.identity.routes import _error, _session_or_401, _validate_origin
from app.modules.identity.service import SessionError, verify_csrf

router = APIRouter(prefix="/api/v1/encounters", tags=["encounters"])

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"in_progress"},
    "in_progress": {"ready_for_discharge", "referred", "transferred"},
    "ready_for_discharge": {"discharged", "in_progress"},
    "discharged": {"finalized"},
}

JSONB_FIELDS = frozenset({
    "medications", "arrival_vitals", "discharge_vitals",
    "administered_treatments", "administered_procedures",
})

DATETIME_FIELDS = frozenset({"arrival_datetime"})

ALL_ENCOUNTER_COLUMNS = """
    e.id, e.clinic_id, e.patient_id, e.appointment_id, e.doctor_id, e.branch_id,
    e.encounter_type, e.status, e.chief_complaint, e.history_present_illness,
    e.examination_findings, e.diagnosis, e.investigations, e.treatment_plan,
    e.medications, e.procedures_performed, e.follow_up_instructions, e.follow_up_date,
    e.arrival_vitals, e.discharge_vitals, e.discharge_notes, e.internal_notes,
    e.created_by, e.finalized_at, e.finalized_by, e.created_at, e.updated_at, e.version,
    e.arrival_mode, e.arrival_datetime, e.attendant_name, e.attendant_phone,
    e.condition_on_arrival, e.known_allergies, e.allergy_status, e.medical_history,
    e.current_medications_text, e.symptom_duration,
    e.gcs_eye, e.gcs_verbal, e.gcs_motor, e.pain_score,
    e.investigation_results, e.clinical_assessment,
    e.administered_treatments, e.administered_procedures,
    e.treatment_response, e.adverse_reactions,
    e.discharge_condition, e.discharge_outcome, e.discharge_destination,
    e.discharge_reason, e.discharge_datetime, e.discharged_by,
    e.discharge_instructions, e.warning_signs, e.medicine_guidance,
    e.follow_up_clinician, e.follow_up_department, e.referral_instructions,
    e.amendment_history
"""


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


def _serialize_jsonb(field: str, val):
    if val is None:
        return None
    if field in ("medications",):
        return json.dumps([m.model_dump() if hasattr(m, "model_dump") else m for m in val])
    if field in ("administered_treatments", "administered_procedures"):
        return json.dumps([item.model_dump() if hasattr(item, "model_dump") else item for item in val])
    if field in ("arrival_vitals", "discharge_vitals"):
        return json.dumps(val.model_dump() if hasattr(val, "model_dump") else val)
    return json.dumps(val)


# ── List ──────────────────────────────────────────────────────────────
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


# ── Detail ────────────────────────────────────────────────────────────
@router.get("/{encounter_id}")
def encounter_detail(
    encounter_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
) -> dict:
    session = _authorized(db, session_token, "clinical.read")
    row = db.execute(text(f"""
        SELECT {ALL_ENCOUNTER_COLUMNS},
               p.full_name AS patient_name, p.patient_number AS mrn,
               p.date_of_birth AS patient_dob, p.allergies_summary AS patient_allergies,
               p.contraindications AS patient_contraindications,
               p.emergency_contact_name, p.emergency_contact_phone, p.emergency_contact_relation,
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


# ── Create ────────────────────────────────────────────────────────────
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
                                     encounter_type, chief_complaint, arrival_vitals, created_by,
                                     arrival_mode, arrival_datetime, attendant_name, attendant_phone,
                                     condition_on_arrival)
        VALUES (:clinic_id, :patient_id, :appointment_id, :doctor_id, :branch_id,
                :encounter_type, :chief_complaint, CAST(:arrival_vitals AS jsonb), :created_by,
                :arrival_mode, :arrival_datetime, :attendant_name, :attendant_phone,
                :condition_on_arrival)
        RETURNING id, patient_id, appointment_id, doctor_id, branch_id, encounter_type,
                  chief_complaint, arrival_vitals, status, version, created_at,
                  arrival_mode, arrival_datetime, attendant_name, attendant_phone, condition_on_arrival
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
        "arrival_mode": payload.arrival_mode,
        "arrival_datetime": payload.arrival_datetime,
        "attendant_name": payload.attendant_name,
        "attendant_phone": payload.attendant_phone,
        "condition_on_arrival": payload.condition_on_arrival,
    }).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="encounter.create", entity_type="encounter_form", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


# ── Update ────────────────────────────────────────────────────────────
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
    if current["status"] in ("discharged", "finalized"):
        raise _error("FORBIDDEN", "A discharged or finalized encounter cannot be edited.", status.HTTP_403_FORBIDDEN)
    if current["version"] != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The encounter changed before this update.", status.HTTP_409_CONFLICT)
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    if not values:
        raise _error("INVALID_INPUT", "At least one field is required.", status.HTTP_400_BAD_REQUEST)
    updates = []
    params: dict = {"clinic_id": session["clinic_id"], "id": encounter_id}
    for field, val in values.items():
        if field in JSONB_FIELDS:
            updates.append(f"{field} = CAST(:{field} AS jsonb)")
            params[field] = _serialize_jsonb(field, val)
        elif field in DATETIME_FIELDS:
            updates.append(f"{field} = CAST(:{field} AS timestamptz)")
            params[field] = val.isoformat() if isinstance(val, datetime) else val
        else:
            updates.append(f"{field} = :{field}")
            params[field] = val
    row = db.execute(text(f"""
        UPDATE encounter_forms SET {', '.join(updates)}, version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :id
        RETURNING {ALL_ENCOUNTER_COLUMNS}
    """), params).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="encounter.update", entity_type="encounter_form", entity_id=encounter_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"fields": sorted(values.keys())})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


# ── Status transition ─────────────────────────────────────────────────
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
    allowed = ALLOWED_TRANSITIONS.get(current["status"], set())
    if payload.status not in allowed:
        raise _error("INVALID_TRANSITION", f"Cannot transition from '{current['status']}' to '{payload.status}'.", status.HTTP_400_BAD_REQUEST)
    extras = ""
    if payload.status == "finalized" and current["status"] != "finalized":
        extras = ", finalized_at = now(), finalized_by = :actor"
    row = db.execute(text(f"""
        UPDATE encounter_forms SET status = :status{extras}, version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :id
        RETURNING id, status, finalized_at, finalized_by, version, updated_at
    """), {"clinic_id": session["clinic_id"], "id": encounter_id, "status": payload.status, "actor": session["user_id"]}).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="encounter.status", entity_type="encounter_form", entity_id=encounter_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"from": current["status"], "to": payload.status})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


# ── Discharge ─────────────────────────────────────────────────────────
@router.post("/{encounter_id}/discharge")
def encounter_discharge(
    encounter_id: UUID,
    payload: EncounterDischarge,
    request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    session = _write_authorized(db, request, session_token, "clinical.manage", csrf_token)
    current = db.execute(text("SELECT version, status FROM encounter_forms WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL FOR UPDATE"), {"clinic_id": session["clinic_id"], "id": encounter_id}).mappings().one_or_none()
    if current is None:
        raise _error("NOT_FOUND", "Encounter not found.", status.HTTP_404_NOT_FOUND)
    if current["status"] != "ready_for_discharge":
        raise _error("INVALID_TRANSITION", "Encounter must be in 'ready_for_discharge' status to discharge.", status.HTTP_400_BAD_REQUEST)
    if current["version"] != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The encounter changed before this update.", status.HTTP_409_CONFLICT)
    discharge_vitals_json = json.dumps(payload.discharge_vitals.model_dump()) if payload.discharge_vitals else None
    row = db.execute(text(f"""
        UPDATE encounter_forms SET
            status = 'discharged',
            discharge_condition = :discharge_condition,
            discharge_outcome = :discharge_outcome,
            discharge_destination = :discharge_destination,
            discharge_reason = :discharge_reason,
            discharge_notes = :discharge_notes,
            discharge_instructions = :discharge_instructions,
            warning_signs = :warning_signs,
            medicine_guidance = :medicine_guidance,
            follow_up_date = :follow_up_date,
            follow_up_instructions = :follow_up_instructions,
            follow_up_clinician = :follow_up_clinician,
            follow_up_department = :follow_up_department,
            referral_instructions = :referral_instructions,
            discharge_vitals = CAST(:discharge_vitals AS jsonb),
            discharge_datetime = now(),
            discharged_by = :actor,
            version = version + 1,
            updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :id
        RETURNING {ALL_ENCOUNTER_COLUMNS}
    """), {
        "clinic_id": session["clinic_id"],
        "id": encounter_id,
        "actor": session["user_id"],
        "discharge_condition": payload.discharge_condition,
        "discharge_outcome": payload.discharge_outcome,
        "discharge_destination": payload.discharge_destination,
        "discharge_reason": payload.discharge_reason,
        "discharge_notes": payload.discharge_notes,
        "discharge_instructions": payload.discharge_instructions,
        "warning_signs": payload.warning_signs,
        "medicine_guidance": payload.medicine_guidance,
        "follow_up_date": payload.follow_up_date,
        "follow_up_instructions": payload.follow_up_instructions,
        "follow_up_clinician": payload.follow_up_clinician,
        "follow_up_department": payload.follow_up_department,
        "referral_instructions": payload.referral_instructions,
        "discharge_vitals": discharge_vitals_json,
    }).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="encounter.discharge", entity_type="encounter_form", entity_id=encounter_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"outcome": payload.discharge_outcome})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


# ── Amend ─────────────────────────────────────────────────────────────
@router.post("/{encounter_id}/amend")
def encounter_amend(
    encounter_id: UUID,
    payload: EncounterAmendment,
    request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    session = _write_authorized(db, request, session_token, "clinical.manage", csrf_token)
    current = db.execute(text("SELECT version, status, amendment_history FROM encounter_forms WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL FOR UPDATE"), {"clinic_id": session["clinic_id"], "id": encounter_id}).mappings().one_or_none()
    if current is None:
        raise _error("NOT_FOUND", "Encounter not found.", status.HTTP_404_NOT_FOUND)
    if current["status"] not in ("discharged", "finalized"):
        raise _error("FORBIDDEN", "Only discharged or finalized encounters can be amended.", status.HTTP_403_FORBIDDEN)
    if current["version"] != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The encounter changed before this update.", status.HTTP_409_CONFLICT)
    safe_fields = {
        "chief_complaint", "history_present_illness", "examination_findings",
        "diagnosis", "investigations", "treatment_plan", "procedures_performed",
        "follow_up_instructions", "discharge_notes", "discharge_instructions",
        "clinical_assessment", "investigation_results", "treatment_response",
    }
    if payload.field not in safe_fields:
        raise _error("INVALID_INPUT", f"Field '{payload.field}' cannot be amended.", status.HTTP_400_BAD_REQUEST)
    history = current["amendment_history"] or []
    entry = {
        "field": payload.field,
        "old_value": payload.old_value,
        "new_value": payload.new_value,
        "reason": payload.reason,
        "amended_by": str(session["user_id"]),
        "amended_at": datetime.now(timezone.utc).isoformat(),
    }
    history.append(entry)
    row = db.execute(text(f"""
        UPDATE encounter_forms
        SET {payload.field} = :new_value,
            amendment_history = CAST(:amendment_history AS jsonb),
            version = version + 1,
            updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :id
        RETURNING id, status, amendment_history, version, updated_at
    """), {
        "clinic_id": session["clinic_id"],
        "id": encounter_id,
        "new_value": payload.new_value,
        "amendment_history": json.dumps(history),
    }).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="encounter.amend", entity_type="encounter_form", entity_id=encounter_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"field": payload.field, "reason": payload.reason})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


# ── Print data ────────────────────────────────────────────────────────
@router.get("/{encounter_id}/print")
def encounter_print(
    encounter_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
) -> dict:
    session = _authorized(db, session_token, "clinical.read")
    row = db.execute(text(f"""
        SELECT {ALL_ENCOUNTER_COLUMNS},
               p.full_name AS patient_name, p.patient_number AS mrn,
               p.date_of_birth AS patient_dob, p.allergies_summary AS patient_allergies,
               p.contraindications AS patient_contraindications,
               p.emergency_contact_name, p.emergency_contact_phone, p.emergency_contact_relation,
               d.public_name AS doctor_name, d.specialty AS doctor_specialty,
               b.name AS branch_name,
               c.name AS clinic_name
        FROM encounter_forms e
        JOIN patients p ON p.clinic_id = e.clinic_id AND p.id = e.patient_id
        JOIN doctor_profiles d ON d.clinic_id = e.clinic_id AND d.id = e.doctor_id
        LEFT JOIN branches b ON b.clinic_id = e.clinic_id AND b.id = e.branch_id
        JOIN clinics c ON c.id = e.clinic_id
        WHERE e.clinic_id = :clinic_id AND e.id = :encounter_id AND e.archived_at IS NULL
    """), {"clinic_id": session["clinic_id"], "encounter_id": encounter_id}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Encounter not found.", status.HTTP_404_NOT_FOUND)
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


# ── Lookup by appointment ─────────────────────────────────────────────
@router.get("/by-appointment/{appointment_id}")
def encounter_by_appointment(
    appointment_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="healthcare_session"),
) -> dict:
    session = _authorized(db, session_token, "clinical.read")
    row = db.execute(text("""
        SELECT e.id, e.status, e.encounter_type, e.created_at
        FROM encounter_forms e
        WHERE e.clinic_id = :clinic_id AND e.appointment_id = :appointment_id AND e.archived_at IS NULL
        ORDER BY e.created_at DESC LIMIT 1
    """), {"clinic_id": session["clinic_id"], "appointment_id": appointment_id}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "No encounter found for this appointment.", status.HTTP_404_NOT_FOUND)
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


# ── Archive ───────────────────────────────────────────────────────────
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

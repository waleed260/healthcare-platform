from __future__ import annotations

import secrets
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.tenant import set_tenant_context
from app.core.security import decode_cursor, encode_cursor
from app.modules.authorization.service import ForbiddenError, require_permission
from app.modules.crm.schemas import CareTeamMemberCreate, CareTeamPolicyUpdate, ConsentCreate, ConsentRevoke, ContactCreate, PatientCreate, PatientMerge, PatientNoteCreate, PatientNoteUpdate, PatientUpdate, TagCreate
from app.modules.identity.routes import _error, _session_or_401, _validate_origin
from app.modules.identity.service import SessionError, verify_csrf
from app.modules.audit.service import record_event

router = APIRouter(prefix="/api/v1/patients", tags=["crm"])
tags_router = APIRouter(prefix="/api/v1/tags", tags=["crm"])


def _normalize_email(value: str | None) -> str | None:
    return value.strip().casefold() if value else None


def _normalize_phone(value: str | None) -> str | None:
    return "".join(character for character in value if character.isdigit() or character == "+") if value else None


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


def _patient_scope_sql(alias: str = "p") -> str:
    """Enforce branch and linked-doctor/care-team object scope for CRM access."""
    return f"""
      AND (
        NOT EXISTS (
          SELECT 1 FROM user_branch_scopes scope
          WHERE scope.clinic_id = :clinic_id AND scope.user_id = :user_id
        )
        OR EXISTS (
          SELECT 1
          FROM appointments scoped_appointment
          JOIN user_branch_scopes scope
            ON scope.clinic_id = scoped_appointment.clinic_id
           AND scope.branch_id = scoped_appointment.branch_id
           AND scope.user_id = :user_id
          WHERE scoped_appointment.clinic_id = :clinic_id
            AND scoped_appointment.patient_id = {alias}.id
        )
      )
      AND (
        EXISTS (
          SELECT 1
          FROM user_roles elevated_roles
          JOIN roles elevated_role ON elevated_role.id = elevated_roles.role_id
          WHERE elevated_roles.clinic_id = :clinic_id
            AND elevated_roles.user_id = :user_id
            AND elevated_role.name IN ('owner', 'manager')
        )
        OR NOT EXISTS (
          SELECT 1
          FROM user_roles doctor_roles
          JOIN roles doctor_role ON doctor_role.id = doctor_roles.role_id
          WHERE doctor_roles.clinic_id = :clinic_id
            AND doctor_roles.user_id = :user_id
            AND doctor_role.name = 'doctor'
        )
        OR EXISTS (
          SELECT 1
          FROM appointments doctor_appointment
          JOIN doctor_profiles linked_doctor
            ON linked_doctor.clinic_id = doctor_appointment.clinic_id
           AND linked_doctor.id = doctor_appointment.doctor_id
          WHERE doctor_appointment.clinic_id = :clinic_id
            AND doctor_appointment.patient_id = {alias}.id
            AND linked_doctor.user_id = :user_id
        )
        OR EXISTS (
          SELECT 1
          FROM patient_care_team care_team
          JOIN doctor_profiles care_team_doctor
            ON care_team_doctor.clinic_id = care_team.clinic_id
           AND care_team_doctor.id = care_team.doctor_id
          WHERE care_team.clinic_id = :clinic_id
            AND care_team.patient_id = {alias}.id
            AND care_team_doctor.user_id = :user_id
            AND care_team_doctor.status = 'active'
            AND care_team_doctor.archived_at IS NULL
        )
      )
    """


def _require_patient(db: Session, session: dict, patient_id: UUID) -> None:
    exists = db.execute(text(f"""
        SELECT 1 FROM patients p
        WHERE p.clinic_id = :clinic_id AND p.id = :patient_id AND p.archived_at IS NULL
        {_patient_scope_sql('p')}
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "patient_id": patient_id}).scalar_one_or_none()
    if exists is None:
        raise _error("NOT_FOUND", "Patient not found.", status.HTTP_404_NOT_FOUND)


def _authoring_doctor(db: Session, session: dict, patient_id: UUID, *, require_care_team: bool) -> UUID:
    """Return the caller's active doctor profile only when it may author notes.

    Private notes require a doctor assigned to this patient through an
    appointment or care-team relationship. Care-team notes require the more
    specific, explicitly managed care-team relationship.
    """
    relationship = """
        EXISTS (
          SELECT 1 FROM patient_care_team care_team
          WHERE care_team.clinic_id = doctor.clinic_id
            AND care_team.patient_id = :patient_id
            AND care_team.doctor_id = doctor.id
        )
    """
    if not require_care_team:
        relationship = f"""({relationship} OR EXISTS (
          SELECT 1 FROM appointments appointment
          WHERE appointment.clinic_id = doctor.clinic_id
            AND appointment.patient_id = :patient_id
            AND appointment.doctor_id = doctor.id
        ))"""
    doctor_id = db.execute(text(f"""
        SELECT doctor.id
        FROM doctor_profiles doctor
        WHERE doctor.clinic_id = :clinic_id
          AND doctor.user_id = :user_id
          AND doctor.status = 'active'
          AND doctor.archived_at IS NULL
          AND EXISTS (
            SELECT 1
            FROM user_roles user_role
            JOIN roles role ON role.id = user_role.role_id
            WHERE user_role.clinic_id = :clinic_id
              AND user_role.user_id = :user_id
              AND role.name = 'doctor'
          )
          AND {relationship}
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "patient_id": patient_id}).scalar_one_or_none()
    if doctor_id is None:
        raise _error("FORBIDDEN", "Only an assigned doctor may author this note.", status.HTTP_403_FORBIDDEN)
    return doctor_id


@tags_router.get("")
def tag_list(request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "patient.read")
    values = decode_cursor(cursor, "tags") if cursor else {}
    if cursor and values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    values = values or {}
    rows = db.execute(text("""
        SELECT id, name, created_at, normalized_name
        FROM tags
        WHERE clinic_id = :clinic_id
          AND (:after_name IS NULL OR normalized_name > :after_name OR (normalized_name = :after_name AND id > :after_id))
        ORDER BY normalized_name, id LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "after_name": values.get("name"), "after_id": UUID(values["id"]) if values.get("id") else None, "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor("tags", {"name": rows[-1]["normalized_name"], "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [{key: value for key, value in dict(row).items() if key != "normalized_name"} for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@tags_router.post("", status_code=status.HTTP_201_CREATED)
def tag_create(payload: TagCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "patient.update", csrf_token)
    name = payload.name.strip()
    try:
        row = db.execute(text("INSERT INTO tags (clinic_id, name, normalized_name) VALUES (:clinic_id, :name, :normalized_name) RETURNING id, name, created_at"), {"clinic_id": session["clinic_id"], "name": name, "normalized_name": name.casefold()}).mappings().one()
    except IntegrityError as exc:
        db.rollback()
        raise _error("DUPLICATE", "A tag with this name already exists.", status.HTTP_409_CONFLICT) from exc
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.get("")
def patient_list(request: Request, search: str | None = Query(default=None, max_length=200), cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "patient.read")
    term = (search or "").strip()
    cursor_values = decode_cursor(cursor, "patients") if cursor else None
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid or expired.", status.HTTP_400_BAD_REQUEST)
    rows = db.execute(text(f"""
        SELECT id, patient_number, full_name, normalized_email, normalized_phone, date_of_birth, status, duplicate_of, version, created_at, updated_at
        FROM patients p
        WHERE p.clinic_id = :clinic_id AND p.archived_at IS NULL AND p.duplicate_of IS NULL
          {_patient_scope_sql('p')}
          AND (:after_name IS NULL OR p.full_name > :after_name OR (p.full_name = :after_name AND p.id > :after_id))
          AND (:term = '' OR p.full_name ILIKE :like_term OR p.normalized_email = :email OR p.normalized_phone = :phone)
        ORDER BY p.full_name, p.id LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "after_name": cursor_values.get("full_name") if cursor_values else None, "after_id": UUID(cursor_values["id"]) if cursor_values else None, "term": term, "like_term": f"%{term}%", "email": _normalize_email(term), "phone": _normalize_phone(term), "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_next and rows:
        next_cursor = encode_cursor("patients", {"full_name": rows[-1]["full_name"], "id": str(rows[-1]["id"])})
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


@router.post("/duplicate-candidates")
def duplicate_candidates(payload: PatientCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    """Return ranked possible matches before a staff member creates a patient."""
    session = _authorized(db, session_token, "patient.read")
    normalized_email = _normalize_email(payload.email)
    normalized_phone = _normalize_phone(payload.phone)
    rows = db.execute(text("""
        SELECT id, patient_number, full_name, normalized_email, normalized_phone,
               date_of_birth, status, version,
               (CASE WHEN :email IS NOT NULL AND normalized_email = :email THEN 8 ELSE 0 END
                + CASE WHEN :phone IS NOT NULL AND normalized_phone = :phone THEN 8 ELSE 0 END
                + CASE WHEN :date_of_birth IS NOT NULL AND date_of_birth = :date_of_birth THEN 4 ELSE 0 END
                + CASE WHEN lower(full_name) = lower(:full_name) THEN 4
                       WHEN full_name ILIKE :name_pattern THEN 1 ELSE 0 END) AS match_score
        FROM patients p
        WHERE p.clinic_id = :clinic_id AND p.archived_at IS NULL AND p.duplicate_of IS NULL
          {_patient_scope_sql('p')}
          AND (
            (:email IS NOT NULL AND normalized_email = :email)
            OR (:phone IS NOT NULL AND normalized_phone = :phone)
            OR (:date_of_birth IS NOT NULL AND date_of_birth = :date_of_birth AND full_name ILIKE :name_pattern)
            OR full_name ILIKE :name_pattern
          )
        ORDER BY match_score DESC, full_name, id
        LIMIT 20
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "email": normalized_email, "phone": normalized_phone, "date_of_birth": payload.date_of_birth, "full_name": payload.full_name.strip(), "name_pattern": f"%{payload.full_name.strip()}%"}).mappings().all()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="patient.duplicate_candidates", entity_type="patient", entity_id=None, outcome="success", request_id=UUID(request.state.request_id), metadata={"candidate_count": len(rows)})
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "review_required": bool(rows)}}


@router.get("/care-policy")
def care_team_policy_get(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    """Return the fail-closed manager access policy for care-team notes."""
    session = _authorized(db, session_token, "clinic.update")
    policy = db.execute(text("""
        SELECT allow_manager_care_team_notes, version, updated_at
        FROM clinic_care_policies
        WHERE clinic_id = :clinic_id
    """), {"clinic_id": session["clinic_id"]}).mappings().one_or_none()
    db.commit()
    data = dict(policy) if policy else {
        "allow_manager_care_team_notes": False,
        "version": 0,
        "updated_at": None,
    }
    return {"data": data, "meta": {"request_id": request.state.request_id}}


@router.patch("/care-policy")
def care_team_policy_update(payload: CareTeamPolicyUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    """Change manager care-team-note access with optimistic locking and audit."""
    session = _write_authorized(db, request, session_token, "clinic.update", csrf_token)
    current = db.execute(text("""
        SELECT version FROM clinic_care_policies
        WHERE clinic_id = :clinic_id
        FOR UPDATE
    """), {"clinic_id": session["clinic_id"]}).scalar_one_or_none()
    if current is None:
        if payload.expected_version != 0:
            raise _error("VERSION_CONFLICT", "The care-team policy changed before update.", status.HTTP_409_CONFLICT)
        policy = db.execute(text("""
            INSERT INTO clinic_care_policies
                (clinic_id, allow_manager_care_team_notes, updated_by_user_id)
            VALUES (:clinic_id, :allow, :actor)
            RETURNING allow_manager_care_team_notes, version, updated_at
        """), {"clinic_id": session["clinic_id"], "allow": payload.allow_manager_care_team_notes, "actor": session["user_id"]}).mappings().one()
    else:
        if current != payload.expected_version:
            raise _error("VERSION_CONFLICT", "The care-team policy changed before update.", status.HTTP_409_CONFLICT)
        policy = db.execute(text("""
            UPDATE clinic_care_policies
            SET allow_manager_care_team_notes = :allow,
                updated_by_user_id = :actor,
                version = version + 1,
                updated_at = now()
            WHERE clinic_id = :clinic_id AND version = :expected_version
            RETURNING allow_manager_care_team_notes, version, updated_at
        """), {"clinic_id": session["clinic_id"], "allow": payload.allow_manager_care_team_notes, "actor": session["user_id"], "expected_version": payload.expected_version}).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="clinic.care_team_policy.update", entity_type="clinic", entity_id=session["clinic_id"], outcome="success", request_id=UUID(request.state.request_id), metadata={"manager_care_team_notes": payload.allow_manager_care_team_notes})
    db.commit()
    return {"data": dict(policy), "meta": {"request_id": request.state.request_id}}


@router.get("/{patient_id}/history")
def patient_history(patient_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "patient.read")
    _require_patient(db, session, patient_id)
    appointments = db.execute(text("""
        SELECT h.id, 'appointment' AS event_type, h.appointment_id AS entity_id,
               h.from_status, h.to_status, h.reason, h.actor_user_id, h.created_at
        FROM appointment_history h
        WHERE h.clinic_id = :clinic_id
          AND h.appointment_id IN (SELECT id FROM appointments WHERE clinic_id = :clinic_id AND patient_id = :patient_id)
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id}).mappings().all()
    merges = db.execute(text("""
        SELECT id, 'merge' AS event_type, source_patient_id AS entity_id,
               NULL AS from_status, NULL AS to_status, reason, actor_user_id, created_at
        FROM patient_merge_events
        WHERE clinic_id = :clinic_id AND (source_patient_id = :patient_id OR target_patient_id = :patient_id)
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id}).mappings().all()
    events = sorted((dict(row) for row in [*appointments, *merges]), key=lambda row: (row["created_at"], str(row["id"])), reverse=True)
    db.commit()
    return {"data": events[:200], "meta": {"request_id": request.state.request_id}}


@router.get("/{patient_id}/care-team")
def care_team_list(patient_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "patient.read")
    _require_patient(db, session, patient_id)
    rows = db.execute(text("""
        SELECT team.doctor_id, doctor.public_name, doctor.specialty, team.created_at
        FROM patient_care_team team
        JOIN doctor_profiles doctor
          ON doctor.clinic_id = team.clinic_id AND doctor.id = team.doctor_id
        WHERE team.clinic_id = :clinic_id AND team.patient_id = :patient_id
          AND doctor.status = 'active' AND doctor.archived_at IS NULL
        ORDER BY doctor.public_name, doctor.id
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.post("/{patient_id}/care-team", status_code=status.HTTP_201_CREATED)
def care_team_add(patient_id: UUID, payload: CareTeamMemberCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "patient.update", csrf_token)
    _require_patient(db, session, patient_id)
    doctor = db.execute(text("""
        SELECT id, public_name, specialty
        FROM doctor_profiles
        WHERE clinic_id = :clinic_id AND id = :doctor_id
          AND status = 'active' AND archived_at IS NULL
    """), {"clinic_id": session["clinic_id"], "doctor_id": payload.doctor_id}).mappings().one_or_none()
    if doctor is None:
        raise _error("NOT_FOUND", "Doctor not found.", status.HTTP_404_NOT_FOUND)
    try:
        membership = db.execute(text("""
            INSERT INTO patient_care_team (clinic_id, patient_id, doctor_id, assigned_by_user_id)
            VALUES (:clinic_id, :patient_id, :doctor_id, :actor)
            RETURNING created_at
        """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "doctor_id": payload.doctor_id, "actor": session["user_id"]}).mappings().one()
    except IntegrityError as exc:
        db.rollback()
        raise _error("DUPLICATE", "This doctor is already on the patient's care team.", status.HTTP_409_CONFLICT) from exc
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="patient.care_team.assign", entity_type="patient", entity_id=patient_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"doctor_id": str(payload.doctor_id)})
    db.commit()
    return {"data": {**dict(doctor), **dict(membership)}, "meta": {"request_id": request.state.request_id}}


@router.delete("/{patient_id}/care-team/{doctor_id}")
def care_team_remove(patient_id: UUID, doctor_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "patient.update", csrf_token)
    _require_patient(db, session, patient_id)
    removed = db.execute(text("""
        DELETE FROM patient_care_team
        WHERE clinic_id = :clinic_id AND patient_id = :patient_id AND doctor_id = :doctor_id
        RETURNING doctor_id
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "doctor_id": doctor_id}).mappings().one_or_none()
    if removed is None:
        raise _error("NOT_FOUND", "Care-team membership not found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="patient.care_team.remove", entity_type="patient", entity_id=patient_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"doctor_id": str(doctor_id)})
    db.commit()
    return {"data": {"doctor_id": doctor_id, "removed": True}, "meta": {"request_id": request.state.request_id}}


@router.get("/{patient_id}")
def patient_detail(patient_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "patient.read")
    patient = db.execute(text(f"SELECT id, patient_number, full_name, normalized_email, normalized_phone, date_of_birth, status, duplicate_of, version, created_at, updated_at FROM patients p WHERE p.clinic_id = :clinic_id AND p.id = :id AND p.archived_at IS NULL {_patient_scope_sql('p')}"), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "id": patient_id}).mappings().one_or_none()
    if patient is None:
        raise _error("NOT_FOUND", "Patient not found.", status.HTTP_404_NOT_FOUND)
    db.commit()
    return {"data": dict(patient), "meta": {"request_id": request.state.request_id}}


@router.patch("/{patient_id}")
def patient_update(patient_id: UUID, payload: PatientUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "patient.update", csrf_token)
    _require_patient(db, session, patient_id)
    current = db.execute(text("SELECT version FROM patients WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL FOR UPDATE"), {"clinic_id": session["clinic_id"], "id": patient_id}).scalar_one_or_none()
    if current is None:
        raise _error("NOT_FOUND", "Patient not found.", status.HTTP_404_NOT_FOUND)
    if current != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The patient changed before update.", status.HTTP_409_CONFLICT)
    values = payload.model_dump(exclude_unset=True)
    updates = []
    params: dict[str, object] = {"clinic_id": session["clinic_id"], "id": patient_id}
    if values.get("full_name") is not None:
        updates.append("full_name = :full_name")
        params["full_name"] = values["full_name"].strip()
    if "email" in values:
        updates.append("normalized_email = :email")
        params["email"] = _normalize_email(values["email"])
    if "phone" in values:
        updates.append("normalized_phone = :phone")
        params["phone"] = _normalize_phone(values["phone"])
    if not updates:
        raise _error("INVALID_INPUT", "At least one patient field is required.", status.HTTP_400_BAD_REQUEST)
    result = db.execute(text(f"UPDATE patients SET {', '.join(updates)}, version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :id RETURNING id, full_name, normalized_email, normalized_phone, version, updated_at"), params).mappings().one()
    db.commit()
    return {"data": dict(result), "meta": {"request_id": request.state.request_id}}


@router.post("", status_code=status.HTTP_201_CREATED)
def patient_create(payload: PatientCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "patient.create", csrf_token)
    normalized_email = _normalize_email(payload.email)
    normalized_phone = _normalize_phone(payload.phone)
    duplicate = db.execute(text("""
        SELECT id FROM patients WHERE clinic_id = :clinic_id AND archived_at IS NULL
          AND ((:email IS NOT NULL AND normalized_email = :email) OR (:phone IS NOT NULL AND normalized_phone = :phone))
        LIMIT 1
    """), {"clinic_id": session["clinic_id"], "email": normalized_email, "phone": normalized_phone}).scalar_one_or_none()
    if duplicate is not None:
        raise _error("DUPLICATE_REVIEW_REQUIRED", "A matching patient already exists and requires review.", status.HTTP_409_CONFLICT)
    patient = db.execute(text("""
        INSERT INTO patients (clinic_id, patient_number, full_name, normalized_email, normalized_phone, date_of_birth)
        VALUES (:clinic_id, :patient_number, :full_name, :email, :phone, :date_of_birth)
        RETURNING id, patient_number, full_name, normalized_email, normalized_phone, date_of_birth, status, version, created_at
    """), {"clinic_id": session["clinic_id"], "patient_number": f"P-{secrets.token_hex(6).upper()}", "full_name": payload.full_name.strip(), "email": normalized_email, "phone": normalized_phone, "date_of_birth": payload.date_of_birth}).mappings().one()
    db.commit()
    return {"data": dict(patient), "meta": {"request_id": request.state.request_id}}


@router.post("/{patient_id}/archive")
def patient_archive(patient_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "patient.archive", csrf_token)
    _require_patient(db, session, patient_id)
    result = db.execute(text("UPDATE patients SET archived_at = now(), status = 'archived', version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL RETURNING id, archived_at, version"), {"clinic_id": session["clinic_id"], "id": patient_id}).mappings().one_or_none()
    if result is None:
        raise _error("NOT_FOUND", "Patient not found.", status.HTTP_404_NOT_FOUND)
    db.commit()
    return {"data": dict(result), "meta": {"request_id": request.state.request_id}}


@router.post("/{patient_id}/merge")
def patient_merge(patient_id: UUID, payload: PatientMerge, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "patient.update", csrf_token)
    _require_patient(db, session, patient_id)
    _require_patient(db, session, payload.target_patient_id)
    if patient_id == payload.target_patient_id:
        raise _error("INVALID_INPUT", "Source and target patients must differ.", status.HTTP_400_BAD_REQUEST)
    rows = db.execute(text("SELECT id FROM patients WHERE clinic_id = :clinic_id AND id IN (:source, :target) AND archived_at IS NULL FOR UPDATE"), {"clinic_id": session["clinic_id"], "source": patient_id, "target": payload.target_patient_id}).scalars().all()
    if len(rows) != 2:
        raise _error("NOT_FOUND", "Patient not found.", status.HTTP_404_NOT_FOUND)
    params = {"clinic_id": session["clinic_id"], "source": patient_id, "target": payload.target_patient_id}
    db.execute(text("UPDATE appointments SET patient_id = :target WHERE clinic_id = :clinic_id AND patient_id = :source"), params)
    db.execute(text("UPDATE follow_up_tasks SET patient_id = :target, updated_at = now() WHERE clinic_id = :clinic_id AND patient_id = :source"), params)
    db.execute(text("UPDATE patient_notes SET patient_id = :target, updated_at = now(), version = version + 1 WHERE clinic_id = :clinic_id AND patient_id = :source"), params)
    db.execute(text("UPDATE consent_records SET patient_id = :target WHERE clinic_id = :clinic_id AND patient_id = :source"), params)
    db.execute(text("UPDATE patient_contacts SET patient_id = :target, updated_at = now() WHERE clinic_id = :clinic_id AND patient_id = :source"), params)
    db.execute(text("INSERT INTO patient_care_team (clinic_id, patient_id, doctor_id, assigned_by_user_id) SELECT clinic_id, :target, doctor_id, assigned_by_user_id FROM patient_care_team WHERE clinic_id = :clinic_id AND patient_id = :source ON CONFLICT DO NOTHING"), params)
    db.execute(text("DELETE FROM patient_care_team WHERE clinic_id = :clinic_id AND patient_id = :source"), params)
    db.execute(text("INSERT INTO patient_tags (clinic_id, patient_id, tag_id) SELECT clinic_id, :target, tag_id FROM patient_tags WHERE clinic_id = :clinic_id AND patient_id = :source ON CONFLICT DO NOTHING"), params)
    db.execute(text("DELETE FROM patient_tags WHERE clinic_id = :clinic_id AND patient_id = :source"), params)
    db.execute(text("UPDATE patients SET duplicate_of = :target, status = 'merged', archived_at = now(), version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :source"), params)
    db.execute(text("INSERT INTO patient_merge_events (clinic_id, source_patient_id, target_patient_id, actor_user_id, reason) VALUES (:clinic_id, :source, :target, :actor, :reason)"), {"clinic_id": session["clinic_id"], "source": patient_id, "target": payload.target_patient_id, "actor": session["user_id"], "reason": payload.reason})
    db.commit()
    return {"data": {"source_patient_id": patient_id, "target_patient_id": payload.target_patient_id, "merged": True}, "meta": {"request_id": request.state.request_id}}


@router.get("/{patient_id}/contacts")
def contact_list(patient_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "patient.read")
    _require_patient(db, session, patient_id)
    rows = db.execute(text("SELECT id, contact_type, value, is_primary, created_at, updated_at FROM patient_contacts WHERE clinic_id = :clinic_id AND patient_id = :patient_id ORDER BY is_primary DESC, created_at"), {"clinic_id": session["clinic_id"], "patient_id": patient_id}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.post("/{patient_id}/contacts", status_code=status.HTTP_201_CREATED)
def contact_create(patient_id: UUID, payload: ContactCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "patient.update", csrf_token)
    _require_patient(db, session, patient_id)
    value = payload.value.strip()
    try:
        row = db.execute(text("INSERT INTO patient_contacts (clinic_id, patient_id, contact_type, value, normalized_value, is_primary) VALUES (:clinic_id, :patient_id, :contact_type, :value, :normalized_value, :is_primary) RETURNING id, contact_type, value, is_primary, created_at"), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "normalized_value": value.casefold(), **payload.model_dump(exclude={"value"}), "value": value}).mappings().one()
    except IntegrityError as exc:
        db.rollback()
        raise _error("NOT_FOUND", "Patient not found.", status.HTTP_404_NOT_FOUND) from exc
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.get("/{patient_id}/notes")
def note_list(patient_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "patient.note.read")
    _require_patient(db, session, patient_id)
    private_filter = " OR (note.visibility = 'private_doctor' AND note.author_user_id = :user_id)"
    try:
        require_permission(db, session["user_id"], session["clinic_id"], "patient.private_note.read")
        private_filter = " OR note.visibility = 'private_doctor'"
    except ForbiddenError:
        pass
    rows = db.execute(text(f"""
        SELECT note.id, note.author_user_id, note.note_type, note.visibility,
               note.body, note.version, note.created_at, note.updated_at
        FROM patient_notes note
        WHERE note.clinic_id = :clinic_id AND note.patient_id = :patient_id
          AND note.archived_at IS NULL
          AND (
            note.visibility = 'clinic'
            OR (
              note.visibility = 'care_team'
              AND (
                EXISTS (
                  SELECT 1
                  FROM patient_care_team care_team
                  JOIN doctor_profiles doctor
                    ON doctor.clinic_id = care_team.clinic_id
                   AND doctor.id = care_team.doctor_id
                  WHERE care_team.clinic_id = :clinic_id
                    AND care_team.patient_id = :patient_id
                    AND doctor.user_id = :user_id
                    AND doctor.status = 'active'
                    AND doctor.archived_at IS NULL
                )
                OR EXISTS (
                  SELECT 1 FROM user_roles user_role
                  JOIN roles role ON role.id = user_role.role_id
                  WHERE user_role.clinic_id = :clinic_id
                    AND user_role.user_id = :user_id
                    AND role.name = 'owner'
                )
                OR (
                  EXISTS (
                    SELECT 1 FROM user_roles user_role
                    JOIN roles role ON role.id = user_role.role_id
                    WHERE user_role.clinic_id = :clinic_id
                      AND user_role.user_id = :user_id
                      AND role.name = 'manager'
                  )
                  AND COALESCE((
                    SELECT allow_manager_care_team_notes
                    FROM clinic_care_policies
                    WHERE clinic_id = :clinic_id
                  ), false)
                )
              )
            )
            {private_filter}
          )
        ORDER BY note.created_at DESC
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "user_id": session["user_id"]}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.post("/{patient_id}/notes", status_code=status.HTTP_201_CREATED)
def note_create(patient_id: UUID, payload: PatientNoteCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "patient.note.write", csrf_token)
    _require_patient(db, session, patient_id)
    if payload.visibility == "private_doctor":
        try:
            require_permission(db, session["user_id"], session["clinic_id"], "patient.private_note.write")
        except ForbiddenError as exc:
            raise _error("FORBIDDEN", "Private doctor notes are restricted.", status.HTTP_403_FORBIDDEN) from exc
        _authoring_doctor(db, session, patient_id, require_care_team=False)
    elif payload.visibility == "care_team":
        _authoring_doctor(db, session, patient_id, require_care_team=True)
    try:
        note = db.execute(text("""
            INSERT INTO patient_notes (clinic_id, patient_id, author_user_id, note_type, visibility, body)
            VALUES (:clinic_id, :patient_id, :author, :note_type, :visibility, :body)
            RETURNING id, author_user_id, note_type, visibility, body, version, created_at
        """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "author": session["user_id"], **payload.model_dump()}).mappings().one()
    except IntegrityError as exc:
        db.rollback()
        raise _error("NOT_FOUND", "Patient not found.", status.HTTP_404_NOT_FOUND) from exc
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="patient_note.create", entity_type="patient_note", entity_id=note["id"], outcome="success", request_id=UUID(request.state.request_id), metadata={"visibility": payload.visibility})
    db.commit()
    return {"data": dict(note), "meta": {"request_id": request.state.request_id}}


@router.patch("/{patient_id}/notes/{note_id}")
def note_update(patient_id: UUID, note_id: UUID, payload: PatientNoteUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "patient.note.write", csrf_token)
    _require_patient(db, session, patient_id)
    note = db.execute(text("SELECT id, version, visibility, author_user_id FROM patient_notes WHERE clinic_id = :clinic_id AND patient_id = :patient_id AND id = :id AND archived_at IS NULL FOR UPDATE"), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "id": note_id}).mappings().one_or_none()
    if note is None:
        raise _error("NOT_FOUND", "Note not found.", status.HTTP_404_NOT_FOUND)
    if note["version"] != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The note changed before update.", status.HTTP_409_CONFLICT)
    target_visibility = payload.visibility or note["visibility"]
    if note["visibility"] == "private_doctor" or target_visibility == "private_doctor":
        try:
            require_permission(db, session["user_id"], session["clinic_id"], "patient.private_note.write")
        except ForbiddenError as exc:
            raise _error("FORBIDDEN", "Private doctor notes are restricted.", status.HTTP_403_FORBIDDEN) from exc
        if note["visibility"] == "private_doctor" and note["author_user_id"] != session["user_id"]:
            raise _error("FORBIDDEN", "Only the authoring doctor may correct a private note.", status.HTTP_403_FORBIDDEN)
        _authoring_doctor(db, session, patient_id, require_care_team=False)
    if note["visibility"] == "care_team" or target_visibility == "care_team":
        _authoring_doctor(db, session, patient_id, require_care_team=True)
    result = db.execute(text("""
        UPDATE patient_notes
        SET body = COALESCE(:body, body), note_type = COALESCE(:note_type, note_type),
            visibility = COALESCE(:visibility, visibility), version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND patient_id = :patient_id AND id = :id
        RETURNING id, note_type, visibility, body, version, updated_at
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "id": note_id, "body": payload.body, "note_type": payload.note_type, "visibility": payload.visibility}).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="patient_note.update", entity_type="patient_note", entity_id=note_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(result), "meta": {"request_id": request.state.request_id}}


@router.get("/{patient_id}/consents")
def consent_list(patient_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "consent.read")
    _require_patient(db, session, patient_id)
    rows = db.execute(text("SELECT id, consent_type, status, version, recorded_by_user_id, recorded_at, withdrawn_at FROM consent_records WHERE clinic_id = :clinic_id AND patient_id = :patient_id ORDER BY recorded_at DESC"), {"clinic_id": session["clinic_id"], "patient_id": patient_id}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.post("/{patient_id}/consents", status_code=status.HTTP_201_CREATED)
def consent_create(patient_id: UUID, payload: ConsentCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "consent.manage", csrf_token)
    _require_patient(db, session, patient_id)
    try:
        consent = db.execute(text("""
            INSERT INTO consent_records (clinic_id, patient_id, consent_type, status, version, recorded_by_user_id, withdrawn_at)
            VALUES (:clinic_id, :patient_id, :consent_type, :status, :version, :actor, CASE WHEN :status = 'withdrawn' THEN now() ELSE NULL END)
            RETURNING id, consent_type, status, version, recorded_by_user_id, recorded_at, withdrawn_at
        """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "actor": session["user_id"], **payload.model_dump()}).mappings().one()
    except IntegrityError as exc:
        db.rollback()
        raise _error("NOT_FOUND", "Patient not found.", status.HTTP_404_NOT_FOUND) from exc
    db.commit()
    return {"data": dict(consent), "meta": {"request_id": request.state.request_id}}


@router.post("/{patient_id}/consents/{consent_id}/revoke")
def consent_revoke(patient_id: UUID, consent_id: UUID, payload: ConsentRevoke, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "consent.manage", csrf_token)
    _require_patient(db, session, patient_id)
    row = db.execute(text("""
        UPDATE consent_records
        SET status = 'withdrawn', withdrawn_at = COALESCE(withdrawn_at, now()), version = version + 1
        WHERE clinic_id = :clinic_id AND patient_id = :patient_id AND id = :id AND version = :expected_version AND status <> 'withdrawn'
        RETURNING id, consent_type, status, version, withdrawn_at
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "id": consent_id, "expected_version": payload.expected_version}).mappings().one_or_none()
    if row is None:
        exists = db.execute(text("SELECT version, status FROM consent_records WHERE clinic_id = :clinic_id AND patient_id = :patient_id AND id = :id"), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "id": consent_id}).mappings().one_or_none()
        if exists is None:
            raise _error("NOT_FOUND", "Consent record not found.", status.HTTP_404_NOT_FOUND)
        if exists["version"] != payload.expected_version:
            raise _error("VERSION_CONFLICT", "The consent record changed before revocation.", status.HTTP_409_CONFLICT)
        raise _error("INVALID_STATE", "The consent record is already withdrawn.", status.HTTP_400_BAD_REQUEST)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="consent.revoke", entity_type="consent_record", entity_id=consent_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}

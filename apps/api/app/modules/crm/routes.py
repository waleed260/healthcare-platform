from __future__ import annotations

import secrets
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.tenant import set_tenant_context
from app.core.security import cursor_payload, encode_cursor
from app.modules.authorization.service import ForbiddenError, require_permission
from app.modules.crm.merge import merge_patients
from app.modules.crm.schemas import CareTeamMemberCreate, CareTeamPolicyUpdate, ConsentCreate, ConsentRevoke, ContactCreate, DischargeCreate, PatientCreate, PatientMerge, PatientNoteCreate, PatientNoteUpdate, PatientUpdate, TagCreate, TransferCreate, VitalCreate
from app.modules.identity.routes import _error, _session_or_401, _validate_origin
from app.modules.identity.service import SessionError, verify_csrf
from app.modules.audit.service import record_event

router = APIRouter(prefix="/api/v1/patients", tags=["crm"])
tags_router = APIRouter(prefix="/api/v1/tags", tags=["crm"])


def _normalize_email(value: str | None) -> str | None:
    return value.strip().casefold() if value else None


def _normalize_phone(value: str | None) -> str | None:
    return "".join(character for character in value if character.isdigit() or character == "+") if value else None


def _like_contains(value: str) -> str:
    """Build a case-insensitive ``contains`` pattern that treats the user's text
    literally. ``%``, ``_`` and the escape char ``\\`` are neutralised so a search
    for e.g. ``50%`` cannot turn into a wildcard scan of every patient. Pair with
    ``ILIKE :pattern ESCAPE '\\'`` in the query."""
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _raise_write_integrity(exc: IntegrityError, *, duplicate_message: str) -> None:
    """Translate a write IntegrityError to a precise status by SQLSTATE rather
    than a blanket 404. A foreign-key miss (23503) means the patient or a linked
    row is gone → 404; a unique violation (23505) is a genuine duplicate → 409
    (as ``tag_create`` already does); any other constraint is unexpected and is
    re-raised so it surfaces as a 500 instead of being mislabelled as a missing
    patient."""
    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
    if sqlstate == "23503":
        raise _error("NOT_FOUND", "Patient not found.", status.HTTP_404_NOT_FOUND) from exc
    if sqlstate == "23505":
        raise _error("DUPLICATE", duplicate_message, status.HTTP_409_CONFLICT) from exc
    raise exc


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
    values = cursor_payload(cursor, "tags", uuid_keys=("id",))
    if cursor and values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid.", status.HTTP_400_BAD_REQUEST)
    values = values or {}
    rows = db.execute(text("""
        SELECT id, name, created_at, normalized_name
        FROM tags
        WHERE clinic_id = :clinic_id
          AND (CAST(:after_name AS text) IS NULL OR normalized_name > CAST(:after_name AS text) OR (normalized_name = CAST(:after_name AS text) AND id > CAST(:after_id AS uuid)))
        ORDER BY normalized_name, id LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "after_name": values.get("name"), "after_id": values.get("id"), "page_size": limit + 1}).mappings().all()
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
def patient_list(request: Request, search: str | None = Query(default=None, max_length=200), status_filter: str | None = Query(default=None, alias="status", max_length=40), cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "patient.read")
    term = (search or "").strip()
    status_value = (status_filter or "").strip().lower() or None
    cursor_values = cursor_payload(cursor, "patients", uuid_keys=("id",))
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid or expired.", status.HTTP_400_BAD_REQUEST)
    cursor_values = cursor_values or {}
    rows = db.execute(text(f"""
        SELECT id, patient_number, full_name, normalized_email, normalized_phone, date_of_birth, status, duplicate_of, version, created_at, updated_at
        FROM patients p
        WHERE p.clinic_id = :clinic_id AND p.archived_at IS NULL AND p.duplicate_of IS NULL
          {_patient_scope_sql('p')}
          AND (CAST(:after_name AS text) IS NULL OR p.full_name > CAST(:after_name AS text) OR (p.full_name = CAST(:after_name AS text) AND p.id > CAST(:after_id AS uuid)))
          AND (:term = '' OR p.full_name ILIKE :like_term ESCAPE '\\' OR p.normalized_email = :email OR p.normalized_phone = :phone)
          AND (:status_value IS NULL OR p.status = :status_value)
        ORDER BY p.full_name, p.id LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "after_name": cursor_values.get("full_name"), "after_id": cursor_values.get("id"), "term": term, "like_term": _like_contains(term), "email": _normalize_email(term), "phone": _normalize_phone(term), "status_value": status_value, "page_size": limit + 1}).mappings().all()
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
    _validate_origin(request)
    session = _authorized(db, session_token, "patient.read")
    normalized_email = _normalize_email(payload.email)
    normalized_phone = _normalize_phone(payload.phone)
    rows = db.execute(text(f"""
        SELECT id, patient_number, full_name, normalized_email, normalized_phone,
               date_of_birth, status, version,
               (CASE WHEN :email IS NOT NULL AND normalized_email = :email THEN 8 ELSE 0 END
                + CASE WHEN :phone IS NOT NULL AND normalized_phone = :phone THEN 8 ELSE 0 END
                + CASE WHEN :date_of_birth IS NOT NULL AND date_of_birth = :date_of_birth THEN 4 ELSE 0 END
                + CASE WHEN lower(full_name) = lower(:full_name) THEN 4
                       WHEN full_name ILIKE :name_pattern ESCAPE '\\' THEN 1 ELSE 0 END) AS match_score
        FROM patients p
        WHERE p.clinic_id = :clinic_id AND p.archived_at IS NULL AND p.duplicate_of IS NULL
          {_patient_scope_sql('p')}
          AND (
            (:email IS NOT NULL AND normalized_email = :email)
            OR (:phone IS NOT NULL AND normalized_phone = :phone)
            OR (:date_of_birth IS NOT NULL AND date_of_birth = :date_of_birth AND full_name ILIKE :name_pattern ESCAPE '\\')
            OR full_name ILIKE :name_pattern ESCAPE '\\'
          )
        ORDER BY match_score DESC, full_name, id
        LIMIT 20
    """), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "email": normalized_email, "phone": normalized_phone, "date_of_birth": payload.date_of_birth, "full_name": payload.full_name.strip(), "name_pattern": _like_contains(payload.full_name.strip())}).mappings().all()
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
        # First-write race: two version-0 writers both read no row and both INSERT.
        # The loser hits the clinic_id PK; map it to the same fail-closed 409 as a
        # stale version instead of surfacing an unhandled 500.
        try:
            policy = db.execute(text("""
                INSERT INTO clinic_care_policies
                    (clinic_id, allow_manager_care_team_notes, updated_by_user_id)
                VALUES (:clinic_id, :allow, :actor)
                RETURNING allow_manager_care_team_notes, version, updated_at
            """), {"clinic_id": session["clinic_id"], "allow": payload.allow_manager_care_team_notes, "actor": session["user_id"]}).mappings().one()
        except IntegrityError as exc:
            db.rollback()
            raise _error("VERSION_CONFLICT", "The care-team policy changed before update.", status.HTTP_409_CONFLICT) from exc
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
        ORDER BY h.created_at DESC
        LIMIT 200
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id}).mappings().all()
    merges = db.execute(text("""
        SELECT id, 'merge' AS event_type, source_patient_id AS entity_id,
               NULL AS from_status, NULL AS to_status, reason, actor_user_id, created_at
        FROM patient_merge_events
        WHERE clinic_id = :clinic_id AND (source_patient_id = :patient_id OR target_patient_id = :patient_id)
        ORDER BY created_at DESC
        LIMIT 200
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id}).mappings().all()
    # Each source is capped at its own newest 200, so the merged newest 200 below
    # is still globally correct while the per-source scan stays bounded.
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
        LIMIT 200
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
    patient = db.execute(text(f"SELECT id, patient_number, full_name, normalized_email, normalized_phone, date_of_birth, status, duplicate_of, emergency_contact_name, emergency_contact_phone, emergency_contact_relation, preferred_communication, contraindications, allergies_summary, version, created_at, updated_at FROM patients p WHERE p.clinic_id = :clinic_id AND p.id = :id AND p.archived_at IS NULL {_patient_scope_sql('p')}"), {"clinic_id": session["clinic_id"], "user_id": session["user_id"], "id": patient_id}).mappings().one_or_none()
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
    changed_fields: list[str] = []
    params: dict[str, object] = {"clinic_id": session["clinic_id"], "id": patient_id}
    if values.get("full_name") is not None:
        updates.append("full_name = :full_name")
        params["full_name"] = values["full_name"].strip()
        changed_fields.append("full_name")
    if "email" in values:
        updates.append("normalized_email = :email")
        params["email"] = _normalize_email(values["email"])
        changed_fields.append("email")
    if "phone" in values:
        updates.append("normalized_phone = :phone")
        params["phone"] = _normalize_phone(values["phone"])
        changed_fields.append("phone")
    if "date_of_birth" in values:
        updates.append("date_of_birth = :date_of_birth")
        params["date_of_birth"] = values["date_of_birth"]
        changed_fields.append("date_of_birth")
    for ext_field in ("emergency_contact_name", "emergency_contact_phone", "emergency_contact_relation", "preferred_communication", "contraindications", "allergies_summary"):
        if ext_field in values:
            updates.append(f"{ext_field} = :{ext_field}")
            params[ext_field] = values[ext_field]
            changed_fields.append(ext_field)
    if not updates:
        raise _error("INVALID_INPUT", "At least one patient field is required.", status.HTTP_400_BAD_REQUEST)
    result = db.execute(text(f"UPDATE patients SET {', '.join(updates)}, version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :id RETURNING id, full_name, normalized_email, normalized_phone, date_of_birth, emergency_contact_name, emergency_contact_phone, emergency_contact_relation, preferred_communication, contraindications, allergies_summary, version, updated_at"), params).mappings().one()
    # Audit the mutation with field *names* only — never PHI values (DOB, name, contacts).
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="patient.update", entity_type="patient", entity_id=patient_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"fields": sorted(changed_fields)})
    db.commit()
    return {"data": dict(result), "meta": {"request_id": request.state.request_id}}


@router.post("", status_code=status.HTTP_201_CREATED)
def patient_create(payload: PatientCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "patient.create", csrf_token)
    normalized_email = _normalize_email(payload.email)
    normalized_phone = _normalize_phone(payload.phone)
    # Soft duplicate gate (intentional trade-off): there is deliberately NO unique
    # index on normalized email/phone, because family members legitimately share a
    # phone or email. This pre-check is best-effort and two concurrent creates can
    # both pass it; the compensating control is the duplicate_candidates ranking
    # (surfaced before create) plus the patient-merge workflow. See
    # docs/blueprint/adr/0001-soft-duplicate-gate.md.
    duplicate = db.execute(text("""
        SELECT id FROM patients WHERE clinic_id = :clinic_id AND archived_at IS NULL
          AND ((:email IS NOT NULL AND normalized_email = :email) OR (:phone IS NOT NULL AND normalized_phone = :phone))
        LIMIT 1
    """), {"clinic_id": session["clinic_id"], "email": normalized_email, "phone": normalized_phone}).scalar_one_or_none()
    if duplicate is not None:
        raise _error("DUPLICATE_REVIEW_REQUIRED", "A matching patient already exists and requires review.", status.HTTP_409_CONFLICT)
    insert_params = {"clinic_id": session["clinic_id"], "full_name": payload.full_name.strip(), "email": normalized_email, "phone": normalized_phone, "date_of_birth": payload.date_of_birth}
    patient = None
    # The random 12-hex patient number has a vanishing but non-zero collision
    # chance against the (clinic_id, patient_number) unique index; retry on the
    # unique violation inside a savepoint so one unlucky draw is not a 500.
    for _ in range(5):
        try:
            with db.begin_nested():
                patient = db.execute(text("""
                    INSERT INTO patients (clinic_id, patient_number, full_name, normalized_email, normalized_phone, date_of_birth)
                    VALUES (:clinic_id, :patient_number, :full_name, :email, :phone, :date_of_birth)
                    RETURNING id, patient_number, full_name, normalized_email, normalized_phone, date_of_birth, status, version, created_at
                """), {**insert_params, "patient_number": f"P-{secrets.token_hex(6).upper()}"}).mappings().one()
            break
        except IntegrityError:
            patient = None
            continue
    if patient is None:
        raise _error("CONFLICT", "Could not allocate a unique patient number; please retry.", status.HTTP_409_CONFLICT)
    # Metadata carries only the non-PHI patient number — never name, contacts, or DOB.
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="patient.create", entity_type="patient", entity_id=patient["id"], outcome="success", request_id=UUID(request.state.request_id), metadata={"patient_number": patient["patient_number"]})
    db.commit()
    return {"data": dict(patient), "meta": {"request_id": request.state.request_id}}


@router.post("/{patient_id}/archive")
def patient_archive(patient_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "patient.archive", csrf_token)
    _require_patient(db, session, patient_id)
    result = db.execute(text("UPDATE patients SET archived_at = now(), status = 'archived', version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL RETURNING id, archived_at, version"), {"clinic_id": session["clinic_id"], "id": patient_id}).mappings().one_or_none()
    if result is None:
        raise _error("NOT_FOUND", "Patient not found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="patient.archive", entity_type="patient", entity_id=patient_id, outcome="success", request_id=UUID(request.state.request_id))
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
    counts = merge_patients(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], source_id=patient_id, target_id=payload.target_patient_id, reason=payload.reason)
    db.commit()
    return {"data": {"source_patient_id": patient_id, "target_patient_id": payload.target_patient_id, "merged": True, "moved": counts}, "meta": {"request_id": request.state.request_id}}


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
        _raise_write_integrity(exc, duplicate_message="This contact already exists for the patient.")
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.get("/{patient_id}/notes")
def note_list(patient_id: UUID, request: Request, cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=100, ge=1, le=200), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "patient.note.read")
    _require_patient(db, session, patient_id)
    cursor_values = cursor_payload(cursor, "patient_notes", uuid_keys=("id",), datetime_keys=("created_at",))
    if cursor and cursor_values is None:
        raise _error("INVALID_INPUT", "The page cursor is invalid or expired.", status.HTTP_400_BAD_REQUEST)
    cursor_values = cursor_values or {}
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
          AND (CAST(:after_id AS uuid) IS NULL OR note.created_at < CAST(:after_created AS timestamptz) OR (note.created_at = CAST(:after_created AS timestamptz) AND note.id < CAST(:after_id AS uuid)))
        ORDER BY note.created_at DESC, note.id DESC
        LIMIT :page_size
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "user_id": session["user_id"],
           "after_created": cursor_values.get("created_at"),
           "after_id": cursor_values.get("id"),
           "page_size": limit + 1}).mappings().all()
    has_next = len(rows) > limit
    rows = list(rows[:limit])
    next_cursor = encode_cursor("patient_notes", {"created_at": rows[-1]["created_at"].isoformat(), "id": str(rows[-1]["id"])}) if has_next and rows else None
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "next_cursor": next_cursor, "limit": limit}}


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
        _raise_write_integrity(exc, duplicate_message="This note already exists.")
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
        _raise_write_integrity(exc, duplicate_message="This consent record already exists.")
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="consent.create", entity_type="consent_record", entity_id=consent["id"], outcome="success", request_id=UUID(request.state.request_id), metadata={"consent_type": consent["consent_type"], "status": consent["status"]})
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


# ── Patient vitals ──────────────────────────────────────────────────────────


@router.get("/{patient_id}/vitals")
def vitals_list(patient_id: UUID, request: Request, vital_type: str | None = Query(default=None, max_length=40), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "patient.read")
    _require_patient(db, session, patient_id)
    rows = db.execute(text("""
        SELECT id, vital_type, label, value_text, value_systolic, value_diastolic, value_numeric, unit, notes, recorded_at, recorded_by, version
        FROM patient_vitals
        WHERE clinic_id = :clinic_id AND patient_id = :patient_id AND archived_at IS NULL
          AND (:vital_type IS NULL OR vital_type = :vital_type)
        ORDER BY recorded_at DESC
        LIMIT :lim
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "vital_type": vital_type, "lim": limit}).mappings().all()
    db.commit()
    return {"data": [dict(r) for r in rows], "meta": {"request_id": request.state.request_id}}


@router.post("/{patient_id}/vitals", status_code=status.HTTP_201_CREATED)
def vitals_create(patient_id: UUID, payload: VitalCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "patient.update", csrf_token)
    _require_patient(db, session, patient_id)
    row = db.execute(text("""
        INSERT INTO patient_vitals (clinic_id, patient_id, vital_type, label, value_text, value_systolic, value_diastolic, value_numeric, unit, notes, recorded_by)
        VALUES (:clinic_id, :patient_id, :vital_type, :label, :value_text, :value_systolic, :value_diastolic, :value_numeric, :unit, :notes, :recorded_by)
        RETURNING id, vital_type, label, value_text, value_systolic, value_diastolic, value_numeric, unit, notes, recorded_at, version
    """), {
        "clinic_id": session["clinic_id"], "patient_id": patient_id, "vital_type": payload.vital_type,
        "label": payload.label, "value_text": payload.value_text,
        "value_systolic": payload.value_systolic, "value_diastolic": payload.value_diastolic,
        "value_numeric": payload.value_numeric, "unit": payload.unit,
        "notes": payload.notes, "recorded_by": session["user_id"],
    }).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="patient_vital.create", entity_type="patient_vital", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.delete("/{patient_id}/vitals/{vital_id}")
def vitals_delete(patient_id: UUID, vital_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "patient.update", csrf_token)
    _require_patient(db, session, patient_id)
    row = db.execute(text("""
        UPDATE patient_vitals SET archived_at = now(), updated_at = now()
        WHERE clinic_id = :clinic_id AND patient_id = :patient_id AND id = :id AND archived_at IS NULL
        RETURNING id
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "id": vital_id}).scalar_one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Vital record not found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="patient_vital.delete", entity_type="patient_vital", entity_id=vital_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": {"id": str(vital_id)}, "meta": {"request_id": request.state.request_id}}


# ── Patient transfers ───────────────────────────────────────────────────────


@router.get("/{patient_id}/transfers")
def transfer_list(patient_id: UUID, request: Request, limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "patient.read")
    _require_patient(db, session, patient_id)
    rows = db.execute(text("""
        SELECT t.id, t.from_branch_id, t.to_branch_id, t.from_doctor_id, t.to_doctor_id,
               t.reason, t.notes, t.status, t.transferred_at, t.created_at, t.version,
               fb.name AS from_branch_name, tb.name AS to_branch_name
        FROM patient_transfers t
        LEFT JOIN branches fb ON fb.clinic_id = t.clinic_id AND fb.id = t.from_branch_id
        LEFT JOIN branches tb ON tb.clinic_id = t.clinic_id AND tb.id = t.to_branch_id
        WHERE t.clinic_id = :clinic_id AND t.patient_id = :patient_id AND t.archived_at IS NULL
        ORDER BY t.created_at DESC LIMIT :lim
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "lim": limit}).mappings().all()
    db.commit()
    return {"data": [dict(r) for r in rows], "meta": {"request_id": request.state.request_id}}


@router.post("/{patient_id}/transfers", status_code=status.HTTP_201_CREATED)
def transfer_create(patient_id: UUID, payload: TransferCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "patient.update", csrf_token)
    _require_patient(db, session, patient_id)
    row = db.execute(text("""
        INSERT INTO patient_transfers (clinic_id, patient_id, from_branch_id, to_branch_id, from_doctor_id, to_doctor_id, reason, notes, requested_by, status)
        VALUES (:clinic_id, :patient_id, :from_branch_id, :to_branch_id, :from_doctor_id, :to_doctor_id, :reason, :notes, :requested_by, 'pending')
        RETURNING id, status, created_at, version
    """), {
        "clinic_id": session["clinic_id"], "patient_id": patient_id,
        "from_branch_id": payload.from_branch_id, "to_branch_id": payload.to_branch_id,
        "from_doctor_id": payload.from_doctor_id, "to_doctor_id": payload.to_doctor_id,
        "reason": payload.reason, "notes": payload.notes, "requested_by": session["user_id"],
    }).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="patient_transfer.create", entity_type="patient_transfer", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


# ── Patient discharges ──────────────────────────────────────────────────────


@router.get("/{patient_id}/discharges")
def discharge_list(patient_id: UUID, request: Request, limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "patient.read")
    _require_patient(db, session, patient_id)
    rows = db.execute(text("""
        SELECT d.id, d.branch_id, d.discharge_type, d.diagnosis, d.treatment_summary,
               d.discharge_instructions, d.follow_up_required, d.follow_up_date,
               d.discharged_at, d.created_at, d.version,
               b.name AS branch_name
        FROM patient_discharges d
        LEFT JOIN branches b ON b.clinic_id = d.clinic_id AND b.id = d.branch_id
        WHERE d.clinic_id = :clinic_id AND d.patient_id = :patient_id AND d.archived_at IS NULL
        ORDER BY d.discharged_at DESC LIMIT :lim
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "lim": limit}).mappings().all()
    db.commit()
    return {"data": [dict(r) for r in rows], "meta": {"request_id": request.state.request_id}}


@router.post("/{patient_id}/discharges", status_code=status.HTTP_201_CREATED)
def discharge_create(patient_id: UUID, payload: DischargeCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "patient.update", csrf_token)
    _require_patient(db, session, patient_id)
    row = db.execute(text("""
        INSERT INTO patient_discharges (clinic_id, patient_id, branch_id, discharge_type, diagnosis, treatment_summary, discharge_instructions, follow_up_required, follow_up_date, discharged_by)
        VALUES (:clinic_id, :patient_id, :branch_id, :discharge_type, :diagnosis, :treatment_summary, :discharge_instructions, :follow_up_required, :follow_up_date, :discharged_by)
        RETURNING id, discharge_type, discharged_at, version
    """), {
        "clinic_id": session["clinic_id"], "patient_id": patient_id,
        "branch_id": payload.branch_id, "discharge_type": payload.discharge_type,
        "diagnosis": payload.diagnosis, "treatment_summary": payload.treatment_summary,
        "discharge_instructions": payload.discharge_instructions,
        "follow_up_required": payload.follow_up_required, "follow_up_date": payload.follow_up_date,
        "discharged_by": session["user_id"],
    }).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="patient_discharge.create", entity_type="patient_discharge", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.audit.service import record_event
from app.modules.authorization.service import ForbiddenError, require_permission
from app.modules.clinical.routes import _authorized, _write_authorized
from app.modules.clinical_forms.schemas import FormResponseCreate, FormResponseSubmit, FormResponseUpdate, FormTemplateCreate, FormTemplateStatus, validate_answers
from app.modules.crm.routes import _require_patient
from app.modules.identity.routes import _error


router = APIRouter(prefix="/api/v1/clinical-forms", tags=["clinical-forms"])
patient_router = APIRouter(prefix="/api/v1/patients", tags=["clinical-forms"])


def _template_for_clinic(db: Session, clinic_id: UUID, template_id: UUID, *, active_only: bool = True) -> dict | None:
    status_clause = "AND status = 'active'" if active_only else ""
    row = db.execute(text(f"SELECT id, specialty_id, form_key, name, field_schema, status, version FROM clinical_form_templates WHERE clinic_id = :clinic_id AND id = :template_id AND archived_at IS NULL {status_clause}"), {"clinic_id": clinic_id, "template_id": template_id}).mappings().one_or_none()
    return dict(row) if row else None


@router.get("/templates")
def template_list(request: Request, specialty_id: UUID | None = Query(default=None), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "clinical.form.read")
    rows = db.execute(text("""
        SELECT id, specialty_id, form_key, name, field_schema, status, version, created_at, updated_at
        FROM clinical_form_templates
        WHERE clinic_id = :clinic_id AND status = 'active' AND archived_at IS NULL
          AND (:specialty_id IS NULL OR specialty_id IS NULL OR specialty_id = :specialty_id)
        ORDER BY name, id
    """), {"clinic_id": session["clinic_id"], "specialty_id": specialty_id}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.post("/templates", status_code=status.HTTP_201_CREATED)
def template_create(payload: FormTemplateCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "clinical.form.manage", csrf_token)
    if payload.specialty_id is not None:
        enabled = db.execute(text("SELECT 1 FROM clinic_specialties WHERE clinic_id = :clinic_id AND specialty_id = :specialty_id AND status = 'active' AND archived_at IS NULL"), {"clinic_id": session["clinic_id"], "specialty_id": payload.specialty_id}).scalar_one_or_none()
        if enabled is None:
            raise _error("NOT_FOUND", "The specialty is not enabled for this clinic.", status.HTTP_404_NOT_FOUND)
    try:
        row = db.execute(text("""
            INSERT INTO clinical_form_templates (clinic_id, specialty_id, form_key, name, field_schema, created_by_user_id)
            VALUES (:clinic_id, :specialty_id, :form_key, :name, CAST(:field_schema AS jsonb), :actor)
            RETURNING id, specialty_id, form_key, name, field_schema, status, version, created_at
        """), {"clinic_id": session["clinic_id"], "specialty_id": payload.specialty_id, "form_key": payload.form_key, "name": payload.name.strip(), "field_schema": __import__("json").dumps(payload.field_schema), "actor": session["user_id"]}).mappings().one()
    except IntegrityError as exc:
        db.rollback()
        raise _error("DUPLICATE", "A form with this key already exists in this clinic.", status.HTTP_409_CONFLICT) from exc
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="clinical_form.template.create", entity_type="clinical_form_template", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.post("/templates/{template_id}/status")
def template_status(template_id: UUID, payload: FormTemplateStatus, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "clinical.form.manage", csrf_token)
    row = db.execute(text("""
        UPDATE clinical_form_templates SET status = :status, archived_at = CASE WHEN :status = 'archived' THEN COALESCE(archived_at, now()) ELSE NULL END, version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :template_id AND version = :expected_version
        RETURNING id, status, version, archived_at, updated_at
    """), {"clinic_id": session["clinic_id"], "template_id": template_id, "status": payload.status, "expected_version": payload.expected_version}).mappings().one_or_none()
    if row is None:
        raise _error("VERSION_CONFLICT", "The form template changed before this update.", status.HTTP_409_CONFLICT)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="clinical_form.template.status", entity_type="clinical_form_template", entity_id=template_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"status": payload.status})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@patient_router.get("/{patient_id}/form-responses")
def response_list(patient_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "clinical.form.read")
    _require_patient(db, session, patient_id)
    rows = db.execute(text("""
        SELECT response.id, response.template_id, template.form_key, template.name, template.specialty_id,
               response.appointment_id, response.response_data, response.status, response.submitted_at,
               response.submitted_by_user_id, response.version, response.created_at, response.updated_at
        FROM clinical_form_responses response
        JOIN clinical_form_templates template ON template.clinic_id = response.clinic_id AND template.id = response.template_id
        WHERE response.clinic_id = :clinic_id AND response.patient_id = :patient_id
        ORDER BY response.updated_at DESC, response.id DESC
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@patient_router.post("/{patient_id}/form-responses", status_code=status.HTTP_201_CREATED)
def response_create(patient_id: UUID, payload: FormResponseCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "clinical.form.manage", csrf_token)
    _require_patient(db, session, patient_id)
    template = _template_for_clinic(db, session["clinic_id"], payload.template_id)
    if template is None:
        raise _error("NOT_FOUND", "The clinical form template is not active.", status.HTTP_404_NOT_FOUND)
    if payload.appointment_id is not None:
        appointment = db.execute(text("SELECT 1 FROM appointments WHERE clinic_id = :clinic_id AND id = :appointment_id AND patient_id = :patient_id AND archived_at IS NULL"), {"clinic_id": session["clinic_id"], "appointment_id": payload.appointment_id, "patient_id": patient_id}).scalar_one_or_none()
        if appointment is None:
            raise _error("NOT_FOUND", "The appointment is not associated with this patient.", status.HTTP_404_NOT_FOUND)
    try:
        validate_answers(template["field_schema"], payload.response_data, require_all=False)
    except ValueError as exc:
        raise _error("INVALID_INPUT", str(exc), status.HTTP_400_BAD_REQUEST) from exc
    row = db.execute(text("""
        INSERT INTO clinical_form_responses (clinic_id, patient_id, template_id, appointment_id, response_data)
        VALUES (:clinic_id, :patient_id, :template_id, :appointment_id, CAST(:response_data AS jsonb))
        RETURNING id, patient_id, template_id, appointment_id, response_data, status, version, created_at, updated_at
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "template_id": payload.template_id, "appointment_id": payload.appointment_id, "response_data": __import__("json").dumps(payload.response_data)}).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="clinical_form.response.create", entity_type="clinical_form_response", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@patient_router.patch("/{patient_id}/form-responses/{response_id}")
def response_update(patient_id: UUID, response_id: UUID, payload: FormResponseUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "clinical.form.manage", csrf_token)
    _require_patient(db, session, patient_id)
    schema = db.execute(text("""
        SELECT t.field_schema FROM clinical_form_responses r JOIN clinical_form_templates t ON t.clinic_id = r.clinic_id AND t.id = r.template_id
        WHERE r.clinic_id = :clinic_id AND r.patient_id = :patient_id AND r.id = :response_id
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "response_id": response_id}).scalar_one_or_none()
    if schema is not None:
        try:
            validate_answers(schema, payload.response_data, require_all=False)
        except ValueError as exc:
            raise _error("INVALID_INPUT", str(exc), status.HTTP_400_BAD_REQUEST) from exc
    row = db.execute(text("""
        UPDATE clinical_form_responses SET response_data = CAST(:response_data AS jsonb), version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND patient_id = :patient_id AND id = :response_id AND status = 'draft' AND version = :expected_version
        RETURNING id, patient_id, template_id, response_data, status, version, updated_at
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "response_id": response_id, "expected_version": payload.expected_version, "response_data": __import__("json").dumps(payload.response_data)}).mappings().one_or_none()
    if row is None:
        raise _error("VERSION_CONFLICT", "The form response changed, was submitted, or was not found.", status.HTTP_409_CONFLICT)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="clinical_form.response.update", entity_type="clinical_form_response", entity_id=response_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@patient_router.post("/{patient_id}/form-responses/{response_id}/submit")
def response_submit(patient_id: UUID, response_id: UUID, payload: FormResponseSubmit, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "clinical.form.manage", csrf_token)
    _require_patient(db, session, patient_id)
    current = db.execute(text("""
        SELECT r.response_data, t.field_schema FROM clinical_form_responses r JOIN clinical_form_templates t ON t.clinic_id = r.clinic_id AND t.id = r.template_id
        WHERE r.clinic_id = :clinic_id AND r.patient_id = :patient_id AND r.id = :response_id AND r.status = 'draft'
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "response_id": response_id}).mappings().one_or_none()
    if current is not None:
        try:
            validate_answers(current["field_schema"], current["response_data"] or {}, require_all=True)
        except ValueError as exc:
            raise _error("INVALID_INPUT", str(exc), status.HTTP_400_BAD_REQUEST) from exc
    row = db.execute(text("""
        UPDATE clinical_form_responses SET status = 'submitted', submitted_at = now(), submitted_by_user_id = :actor, version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND patient_id = :patient_id AND id = :response_id AND status = 'draft' AND version = :expected_version
        RETURNING id, patient_id, template_id, status, submitted_at, submitted_by_user_id, version, updated_at
    """), {"clinic_id": session["clinic_id"], "patient_id": patient_id, "response_id": response_id, "expected_version": payload.expected_version, "actor": session["user_id"]}).mappings().one_or_none()
    if row is None:
        raise _error("VERSION_CONFLICT", "The form response changed, was submitted, or was not found.", status.HTTP_409_CONFLICT)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="clinical_form.response.submit", entity_type="clinical_form_response", entity_id=response_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}

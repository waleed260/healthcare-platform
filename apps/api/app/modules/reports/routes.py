from __future__ import annotations

import csv
import io
import json
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Request, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.tenant import set_tenant_context
from app.modules.audit.service import record_event
from app.modules.authorization.service import ForbiddenError, require_permission
from app.modules.identity.routes import _error, _session_or_401, _validate_origin
from app.modules.identity.service import SessionError, verify_csrf
from app.modules.reports.registry import SOURCES, catalog, run_report
from app.modules.reports.schemas import ReportConfig, SavedReportCreate, SavedReportDuplicate, SavedReportUpdate

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


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


def _require_source_permission(db: Session, session: dict, source: str) -> None:
    """A report may read a module that needs its own permission (e.g. package_sales)."""
    perm = SOURCES[source].permission
    if perm == "report.read":
        return
    try:
        require_permission(db, session["user_id"], session["clinic_id"], perm)
    except ForbiddenError as exc:
        raise _error("FORBIDDEN", f"You need the {perm} permission to run this report.", status.HTTP_403_FORBIDDEN) from exc


@router.get("/sources")
def report_sources(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    _authorized(db, session_token, "report.read")
    db.commit()
    return {"data": catalog(), "meta": {"request_id": request.state.request_id}}


@router.post("/run")
def report_run_adhoc(payload: ReportConfig, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "report.read")
    _require_source_permission(db, session, payload.source)
    result = run_report(db, session["clinic_id"], payload)
    db.commit()
    return {"data": result, "meta": {"request_id": request.state.request_id}}


@router.get("")
def report_list(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "report.read")
    rows = db.execute(text("""
        SELECT id, name, description, source, config, status, created_by_user_id, last_run_at, version, created_at, updated_at
        FROM saved_reports WHERE clinic_id = :c AND status = 'active' ORDER BY name, id
    """), {"c": session["clinic_id"]}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.post("", status_code=status.HTTP_201_CREATED)
def report_create(payload: SavedReportCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "report.manage", csrf_token)
    row = db.execute(text("""
        INSERT INTO saved_reports (clinic_id, name, description, source, config, created_by_user_id)
        VALUES (:c, :name, :description, :source, CAST(:config AS jsonb), :user_id)
        RETURNING id, name, description, source, config, status, created_by_user_id, last_run_at, version, created_at, updated_at
    """), {"c": session["clinic_id"], "name": payload.name, "description": payload.description, "source": payload.config.source, "config": json.dumps(payload.config.model_dump(mode="json")), "user_id": session["user_id"]}).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="report.create", entity_type="saved_report", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


def _load_report(db: Session, clinic_id: UUID, report_id: UUID) -> dict:
    row = db.execute(text("""
        SELECT id, name, description, source, config, status, created_by_user_id, last_run_at, version, created_at, updated_at
        FROM saved_reports WHERE clinic_id = :c AND id = :id
    """), {"c": clinic_id, "id": report_id}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Report not found.", status.HTTP_404_NOT_FOUND)
    return dict(row)


@router.get("/{report_id}")
def report_get(report_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "report.read")
    row = _load_report(db, session["clinic_id"], report_id)
    db.commit()
    return {"data": row, "meta": {"request_id": request.state.request_id}}


@router.put("/{report_id}")
def report_update(report_id: UUID, payload: SavedReportUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "report.manage", csrf_token)
    assignments, params = [], {"c": session["clinic_id"], "id": report_id, "ev": payload.expected_version}
    if payload.name is not None:
        assignments.append("name = :name"); params["name"] = payload.name
    if payload.description is not None:
        assignments.append("description = :description"); params["description"] = payload.description
    if payload.config is not None:
        assignments.append("source = :source"); params["source"] = payload.config.source
        assignments.append("config = CAST(:config AS jsonb)"); params["config"] = json.dumps(payload.config.model_dump(mode="json"))
    assignments += ["version = version + 1", "updated_at = now()"]
    updated = db.execute(text(f"""
        UPDATE saved_reports SET {", ".join(assignments)}
        WHERE clinic_id = :c AND id = :id AND version = :ev AND status = 'active'
        RETURNING id, name, description, source, config, status, created_by_user_id, last_run_at, version, created_at, updated_at
    """), params).mappings().one_or_none()
    if updated is None:
        _load_report(db, session["clinic_id"], report_id)  # raises 404 if missing
        raise _error("VERSION_CONFLICT", "The report changed before this edit; reload and retry.", status.HTTP_409_CONFLICT)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="report.update", entity_type="saved_report", entity_id=report_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(updated), "meta": {"request_id": request.state.request_id}}


@router.post("/{report_id}/duplicate", status_code=status.HTTP_201_CREATED)
def report_duplicate(report_id: UUID, payload: SavedReportDuplicate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "report.manage", csrf_token)
    source = _load_report(db, session["clinic_id"], report_id)
    row = db.execute(text("""
        INSERT INTO saved_reports (clinic_id, name, description, source, config, created_by_user_id)
        VALUES (:c, :name, :description, :source, CAST(:config AS jsonb), :user_id)
        RETURNING id, name, description, source, config, status, created_by_user_id, last_run_at, version, created_at, updated_at
    """), {"c": session["clinic_id"], "name": payload.name, "description": source["description"], "source": source["source"], "config": json.dumps(source["config"]), "user_id": session["user_id"]}).mappings().one()
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.post("/{report_id}/archive")
def report_archive(report_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "report.manage", csrf_token)
    updated = db.execute(text("UPDATE saved_reports SET status = 'archived', updated_at = now(), version = version + 1 WHERE clinic_id = :c AND id = :id AND status = 'active' RETURNING id"), {"c": session["clinic_id"], "id": report_id}).scalar_one_or_none()
    if updated is None:
        raise _error("NOT_FOUND", "Active report not found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="report.archive", entity_type="saved_report", entity_id=report_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": {"id": updated, "archived": True}, "meta": {"request_id": request.state.request_id}}


def _run_saved(db: Session, session: dict, report_id: UUID) -> tuple[dict, dict]:
    row = _load_report(db, session["clinic_id"], report_id)
    config = ReportConfig(**row["config"])  # re-validates against the current registry
    _require_source_permission(db, session, config.source)
    result = run_report(db, session["clinic_id"], config)
    db.execute(text("UPDATE saved_reports SET last_run_at = now() WHERE clinic_id = :c AND id = :id"), {"c": session["clinic_id"], "id": report_id})
    return row, result


@router.post("/{report_id}/run")
def report_run_saved(report_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "report.read")
    row, result = _run_saved(db, session, report_id)
    db.commit()
    return {"data": {"report": {"id": row["id"], "name": row["name"]}, **result}, "meta": {"request_id": request.state.request_id}}


@router.get("/{report_id}/export")
def report_export_csv(report_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> Response:
    session = _authorized(db, session_token, "report.read")
    row, result = _run_saved(db, session, report_id)
    db.commit()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([col["label"] for col in result["columns"]])
    keys = [col["key"] for col in result["columns"]]
    for data_row in result["rows"]:
        writer.writerow(["" if data_row.get(k) is None else data_row.get(k) for k in keys])
    filename = "".join(c for c in row["name"] if c.isalnum() or c in (" ", "-", "_")).strip().replace(" ", "_") or "report"
    return Response(content=buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'})

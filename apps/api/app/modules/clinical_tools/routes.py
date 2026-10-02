from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.audit.service import record_event
from app.modules.clinical.routes import _authorized, _write_authorized
from app.modules.clinical_tools.schemas import ToolStateUpsert, validate_tool_state
from app.modules.crm.routes import _require_patient
from app.modules.identity.routes import _error

router = APIRouter(prefix="/api/v1/patients", tags=["clinical-tools"])

_COLUMNS = "tool_key, state, version, updated_at"


@router.get("/{patient_id}/tool-states")
def tool_state_list(patient_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "clinical.read")
    _require_patient(db, session, patient_id)
    rows = db.execute(text(f"SELECT {_COLUMNS} FROM clinical_tool_states WHERE clinic_id = :c AND patient_id = :p ORDER BY tool_key"),
                      {"c": session["clinic_id"], "p": patient_id}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.put("/{patient_id}/tool-states/{tool_key}")
def tool_state_upsert(patient_id: UUID, tool_key: str, payload: ToolStateUpsert, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "clinical.manage", csrf_token)
    _require_patient(db, session, patient_id)
    if tool_key != payload.tool_key:
        raise _error("INVALID_INPUT", "The tool key in the path and body must match.", status.HTTP_400_BAD_REQUEST)
    try:
        state = validate_tool_state(tool_key, payload.state)
    except ValueError as exc:
        raise _error("INVALID_INPUT", str(exc), status.HTTP_400_BAD_REQUEST) from exc
    row = db.execute(text(f"""
        INSERT INTO clinical_tool_states (clinic_id, patient_id, tool_key, state, updated_by_user_id)
        VALUES (:c, :p, :tool_key, CAST(:state AS jsonb), :actor)
        ON CONFLICT (clinic_id, patient_id, tool_key)
        DO UPDATE SET state = EXCLUDED.state, version = clinical_tool_states.version + 1, updated_by_user_id = EXCLUDED.updated_by_user_id, updated_at = now()
        RETURNING {_COLUMNS}
    """), {"c": session["clinic_id"], "p": patient_id, "tool_key": tool_key, "state": json.dumps(state), "actor": session["user_id"]}).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="clinical_tool.save", entity_type="clinical_tool_state", entity_id=None, outcome="success", request_id=UUID(request.state.request_id), metadata={"tool_key": tool_key})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}

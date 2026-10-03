from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.modules.blueprint_core import routes
from app.modules.blueprint_core.schemas import LeadActivityCreate, LeadUpdate
from app.modules.authorization.service import ForbiddenError


@pytest.mark.parametrize("kind", ["call", "note", "message"])
def test_activity_strips_body_and_rejects_due_date_for_non_follow_up(kind):
    assert LeadActivityCreate(kind=kind, body="  Contacted prospect  ").body == (
        "Contacted prospect"
    )
    with pytest.raises(ValidationError):
        LeadActivityCreate(kind=kind, body="Note", due_at="2026-10-02T09:00:00Z")


@pytest.mark.parametrize("payload", [
    {"kind": "note", "body": "   "},
    {"kind": "follow_up", "body": "Call back"},
    {"kind": "follow_up", "body": "Call back", "due_at": "2026-10-02T09:00:00"},
    {"kind": "note", "body": "Note", "actor_user_id": str(uuid4())},
])
def test_activity_rejects_invalid_body_date_and_client_supplied_author(payload):
    with pytest.raises(ValidationError):
        LeadActivityCreate(**payload)


def test_follow_up_accepts_timezone_and_optional_lead_fields_can_be_cleared():
    activity = LeadActivityCreate(
        kind="follow_up", body="Call back", due_at="2026-10-02T14:00:00+05:00",
    )
    assert activity.due_at.utcoffset().total_seconds() == 18000
    assert LeadUpdate(expected_version=1, assigned_to_user_id=None).model_dump(
        exclude_unset=True,
    ) == {"expected_version": 1, "assigned_to_user_id": None}
    with pytest.raises(ValidationError):
        LeadUpdate(expected_version=1, status=None)


@pytest.mark.parametrize("operation,permission", [
    ("read", "lead.read"), ("write", "lead.manage"),
])
def test_activity_requires_server_permission(monkeypatch, operation, permission):
    db = Mock()
    session = {"clinic_id": uuid4(), "user_id": uuid4()}
    request = SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))
    monkeypatch.setattr(routes, "_session_or_401", lambda *args: session)
    monkeypatch.setattr(routes, "set_tenant_context", lambda *args: None)
    monkeypatch.setattr(routes, "_validate_origin", lambda *args: None)
    guard = Mock(side_effect=ForbiddenError("denied"))
    monkeypatch.setattr(routes, "require_permission", guard)
    with pytest.raises(HTTPException) as error:
        if operation == "read":
            routes.lead_activity_list(uuid4(), request, None, 50, db, "session")
        else:
            routes.lead_activity_create(
                uuid4(), LeadActivityCreate(kind="note", body="Note"),
                request, db, "session", "csrf",
            )
    assert error.value.status_code == 403
    assert guard.call_args.args[-1] == permission
    db.execute.assert_not_called()


def test_activity_creation_requires_csrf(monkeypatch):
    db = Mock()
    session = {"clinic_id": uuid4(), "user_id": uuid4()}
    monkeypatch.setattr(routes, "_authorized", lambda *args: session)
    monkeypatch.setattr(routes, "_validate_origin", lambda *args: None)
    with pytest.raises(HTTPException) as error:
        routes.lead_activity_create(
            uuid4(), LeadActivityCreate(kind="note", body="Note"), Mock(), db, "session", None,
        )
    assert error.value.detail["error"]["code"] == "CSRF_REQUIRED"
    db.execute.assert_not_called()


@pytest.fixture
def context(monkeypatch):
    session = {"clinic_id": uuid4(), "user_id": uuid4()}
    request = SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))
    monkeypatch.setattr(routes, "_authorized", lambda *args: session)
    monkeypatch.setattr(routes, "_write_authorized", lambda *args: session)
    audit = Mock()
    monkeypatch.setattr(routes, "record_event", audit)
    return session, request, audit


def test_activity_creation_records_server_author_and_audits_without_body(context):
    session, request, audit = context
    lead_id, activity_id = uuid4(), uuid4()
    db = Mock()
    db.execute.side_effect = [
        Mock(scalar_one_or_none=lambda: lead_id),
        Mock(mappings=lambda: Mock(one=lambda: {"id": activity_id, "kind": "call"})),
    ]
    result = routes.lead_activity_create(
        lead_id, LeadActivityCreate(kind="call", body="Sensitive conversation"),
        request, db, "session", "csrf",
    )
    assert result["data"]["id"] == activity_id
    params = db.execute.call_args_list[1].args[1]
    assert params["clinic_id"] == session["clinic_id"]
    assert params["actor_user_id"] == session["user_id"]
    assert audit.call_args.kwargs["metadata"] == {"lead_id": str(lead_id), "kind": "call"}
    db.commit.assert_called_once()


def test_missing_lead_does_not_insert_activity(context):
    _, request, audit = context
    db = Mock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    with pytest.raises(HTTPException) as error:
        routes.lead_activity_create(
            uuid4(), LeadActivityCreate(kind="note", body="Note"), request, db, "s", "c",
        )
    assert error.value.status_code == 404
    assert db.execute.call_count == 1
    audit.assert_not_called()
    db.commit.assert_not_called()


def test_activity_pagination_and_cursor_are_bound_to_tenant_and_lead(context, monkeypatch):
    session, request, _ = context
    lead_id = uuid4()
    created_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    rows = [{"id": uuid4(), "created_at": created_at} for _ in range(3)]
    encoded = Mock(return_value="next-page")
    monkeypatch.setattr(routes, "encode_cursor", encoded)
    db = Mock()
    db.execute.side_effect = [
        Mock(scalar_one_or_none=lambda: lead_id),
        Mock(mappings=lambda: Mock(all=lambda: rows)),
    ]
    result = routes.lead_activity_list(lead_id, request, None, 2, db, "session")
    assert len(result["data"]) == 2
    assert result["meta"]["next_cursor"] == "next-page"
    assert encoded.call_args.args[0] == f"lead-activities:{session['clinic_id']}:{lead_id}"
    assert encoded.call_args.args[1]["id"] == str(rows[1]["id"])
    assert db.execute.call_args_list[1].args[1]["page_size"] == 3


def test_invalid_activity_cursor_does_not_read_history(context, monkeypatch):
    _, request, _ = context
    monkeypatch.setattr(routes, "decode_cursor", lambda *args: None)
    db = Mock()
    db.execute.return_value.scalar_one_or_none.return_value = uuid4()
    with pytest.raises(HTTPException) as error:
        routes.lead_activity_list(uuid4(), request, "bad-cursor", 2, db, "session")
    assert error.value.status_code == 400
    assert db.execute.call_count == 1


@pytest.mark.parametrize("lead", [
    {"status": "converted", "converted_to_patient_id": uuid4(), "version": 1},
    {"status": "new", "converted_to_patient_id": uuid4(), "version": 1},
])
def test_converted_lead_cannot_reenter_pipeline(context, lead):
    _, request, audit = context
    db = Mock()
    db.execute.side_effect = [
        Mock(scalar_one_or_none=lambda: uuid4()),  # _require_lead scope check passes
        Mock(mappings=lambda: Mock(one_or_none=lambda: lead)),  # FOR UPDATE select
    ]
    with pytest.raises(HTTPException) as error:
        routes.lead_update(
            uuid4(), LeadUpdate(expected_version=1, status="contacted"),
            request, db, "session", "csrf",
        )
    assert error.value.status_code == 409
    assert error.value.detail["error"]["code"] == "LEAD_CONVERTED"
    audit.assert_not_called()
    assert db.execute.call_count == 2


def test_stale_pipeline_update_cannot_overwrite_conversion(context):
    _, request, audit = context
    db = Mock()
    db.execute.side_effect = [
        Mock(scalar_one_or_none=lambda: uuid4()),  # _require_lead scope check passes
        Mock(mappings=lambda: Mock(one_or_none=lambda: {
            "status": "converted", "converted_to_patient_id": uuid4(), "version": 2,
        })),
    ]
    with pytest.raises(HTTPException) as error:
        routes.lead_update(
            uuid4(), LeadUpdate(expected_version=1, status="contacted"),
            request, db, "session", "csrf",
        )
    assert error.value.detail["error"]["code"] == "VERSION_CONFLICT"
    audit.assert_not_called()


@pytest.mark.parametrize("operation", ["update", "convert"])
def test_convert_and_update_reject_out_of_scope_lead_before_mutation(context, operation):
    """M3: convert/update share _require_lead, so an out-of-specialty/branch lead
    is 404 and nothing is written or audited before the scope check."""
    from app.modules.blueprint_core.schemas import LeadConvert

    _, request, audit = context
    db = Mock()
    db.execute.return_value.scalar_one_or_none.return_value = None  # _require_lead miss
    with pytest.raises(HTTPException) as error:
        if operation == "update":
            routes.lead_update(
                uuid4(), LeadUpdate(expected_version=1, status="contacted"),
                request, db, "session", "csrf",
            )
        else:
            routes.lead_convert(uuid4(), LeadConvert(), request, db, "session", "csrf")
    assert error.value.status_code == 404
    assert db.execute.call_count == 1  # only the scope check ran; no mutation
    audit.assert_not_called()
    db.commit.assert_not_called()


def test_converted_lead_retains_editable_notes(context):
    _, request, audit = context
    db = Mock()
    db.execute.side_effect = [
        Mock(scalar_one_or_none=lambda: uuid4()),  # _require_lead scope check passes
        Mock(mappings=lambda: Mock(one_or_none=lambda: {
            "status": "converted", "converted_to_patient_id": uuid4(), "version": 2,
        })),
        Mock(mappings=lambda: Mock(one_or_none=lambda: {"version": 3, "notes": None})),
    ]
    result = routes.lead_update(
        uuid4(), LeadUpdate(expected_version=2, notes=None), request, db, "session", "csrf",
    )
    assert result["data"]["version"] == 3
    assert db.execute.call_args_list[2].args[1]["notes"] is None
    audit.assert_called_once()
    db.commit.assert_called_once()

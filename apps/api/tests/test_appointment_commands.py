from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.appointments.schemas import AppointmentRescheduleRequest, AppointmentTransitionRequest, PublicBookingRequest
from app.modules.appointments import routes as appointment_routes


def test_transition_contract_requires_version_and_closed_state_set() -> None:
    command = AppointmentTransitionRequest(to_status="confirmed", expected_version=2)
    assert command.expected_version == 2
    with pytest.raises(ValidationError):
        AppointmentTransitionRequest(to_status="completed", expected_version=0)


def test_reschedule_requires_timezone_and_reason_shape() -> None:
    command = AppointmentRescheduleRequest(starts_at=datetime(2026, 10, 1, 9, tzinfo=timezone.utc), expected_version=1, reason="Synthetic schedule change")
    assert command.starts_at.tzinfo is not None


def test_appointment_authorization_passes_object_branch_scope(monkeypatch) -> None:
    calls = []
    session = {"clinic_id": "clinic-1", "user_id": "user-1"}
    monkeypatch.setattr(appointment_routes, "_session_or_401", lambda db, token: session)
    monkeypatch.setattr(appointment_routes, "set_tenant_context", lambda db, clinic_id, user_id: None)
    monkeypatch.setattr(
        appointment_routes,
        "require_permission",
        lambda db, user_id, clinic_id, permission, branch_id=None: calls.append((permission, branch_id)),
    )

    assert appointment_routes._staff_authorized(SimpleNamespace(), "session", "appointment.cancel", branch_id="branch-1") == session
    assert calls == [("appointment.cancel", "branch-1")]


def test_idempotent_booking_replay_returns_committed_result(monkeypatch) -> None:
    clinic_id = uuid4()
    db = Mock()
    result = Mock()
    result.mappings.return_value.one_or_none.return_value = {
        "id": uuid4(),
        "reference": "BK-SYNTHETIC",
        "status": "requested",
        "idempotency_body_hash": "a" * 64,
    }
    db.execute.return_value = result
    monkeypatch.setattr(appointment_routes, "set_tenant_context", lambda *_args: None)
    request = SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))

    replay = appointment_routes._replay_idempotent_booking(db, clinic_id, "same-key", "a" * 64, request)

    assert replay["data"] == {"reference": "BK-SYNTHETIC", "status": "requested"}
    db.commit.assert_called_once()


def test_public_idempotency_body_hash_query_is_tenant_scoped(monkeypatch) -> None:
    clinic_id = uuid4()
    appointment_id = uuid4()
    branch_id = uuid4()
    service_id = uuid4()
    payload = PublicBookingRequest(
        branch_id=branch_id,
        service_id=service_id,
        starts_at=datetime(2030, 1, 1, 9, tzinfo=timezone.utc),
        full_name="Synthetic Patient",
    )
    import hashlib
    import json

    body_hash = hashlib.sha256(json.dumps(payload.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
    clinic_result = Mock()
    clinic_result.scalar_one_or_none.return_value = clinic_id
    existing_result = Mock()
    existing_result.mappings.return_value.one_or_none.return_value = {
        "id": appointment_id,
        "reference": "BK-SYNTHETIC",
        "status": "requested",
    }
    hash_result = Mock()
    hash_result.scalar_one.return_value = body_hash
    db = Mock()
    db.execute.side_effect = [clinic_result, existing_result, hash_result]
    monkeypatch.setattr(appointment_routes, "set_tenant_context", lambda *_args: None)
    request = SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))

    replay = appointment_routes.create_public_booking(
        payload,
        request,
        db,
        idempotency_key="same-key",
        clinic_slug="synthetic-care",
    )

    assert replay["data"] == {"reference": "BK-SYNTHETIC", "status": "requested"}
    assert db.execute.call_args_list[2].args[1]["clinic_id"] == clinic_id

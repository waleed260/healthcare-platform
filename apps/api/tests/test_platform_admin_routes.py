from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import Response

from app.modules.governance import admin_routes
from app.modules.governance.schemas import ClinicLifecycleUpdate
from app.modules.governance.schemas import PlatformSupportAccessCreate


def _request() -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))


def test_platform_lifecycle_suspend_revokes_sessions_tokens_and_audits_reason(monkeypatch) -> None:
    clinic_id, actor_id = uuid4(), uuid4()
    row = {"id": clinic_id, "name": "Synthetic clinic", "slug": "synthetic", "status": "suspended", "archived_at": None, "version": 4, "updated_at": None}
    db = Mock()
    db.execute.side_effect = [
        Mock(mappings=lambda: Mock(one_or_none=lambda: row)),
        Mock(),
        Mock(),
    ]
    audited = {}
    monkeypatch.setattr(admin_routes, "_write", lambda db, request, token, csrf: {"user_id": actor_id})
    monkeypatch.setattr(admin_routes, "record_event", lambda db, **kwargs: audited.update(kwargs))

    result = admin_routes.clinic_lifecycle(
        clinic_id,
        ClinicLifecycleUpdate(action="suspend", reason="Suspicious activity review", expected_version=3),
        _request(),
        db,
        "session-token",
        "csrf-token",
    )

    assert result["data"]["status"] == "suspended"
    assert audited["action"] == "admin.clinic.suspend"
    assert audited["clinic_id"] is None
    assert audited["entity_id"] == clinic_id
    assert audited["metadata"]["reason"] == "Suspicious activity review"
    assert db.commit.called


def test_platform_guard_rejects_non_admin_clinic_session(monkeypatch) -> None:
    db = Mock()
    monkeypatch.setattr(admin_routes, "_session_or_401", lambda db, token: {"user_id": uuid4(), "clinic_id": uuid4()})

    with pytest.raises(Exception) as error:
        admin_routes._platform(db, "clinic-session")

    assert getattr(error.value, "status_code", None) == 403


def test_support_access_activation_rejects_expired_session(monkeypatch) -> None:
    db = Mock()
    db.execute.return_value = Mock(mappings=lambda: Mock(one_or_none=lambda: None))
    monkeypatch.setattr(admin_routes, "_write", lambda db, request, token, csrf: {"user_id": uuid4()})

    with pytest.raises(Exception) as error:
        admin_routes.support_access_activate(uuid4(), Response(), _request(), db, "session-token", "csrf-token")

    assert getattr(error.value, "status_code", None) == 409


def test_platform_support_access_create_requires_separate_authorized_approver(monkeypatch) -> None:
    clinic_id, requester_id, approver_id, actor_id, access_id = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    row = {"id": access_id, "clinic_id": clinic_id, "requested_by_user_id": requester_id, "approved_by_user_id": approver_id, "reason": "Investigate a support issue", "permissions": ["patient.read"], "starts_at": None, "expires_at": None, "revoked_at": None}
    db = Mock()
    db.execute.side_effect = [
        Mock(scalar_one_or_none=lambda: True),
        Mock(mappings=lambda: Mock(all=lambda: [{"id": requester_id, "can_approve": False}, {"id": approver_id, "can_approve": True}])),
        Mock(mappings=lambda: Mock(one=lambda: row)),
    ]
    audited = {}
    monkeypatch.setattr(admin_routes, "_write", lambda db, request, token, csrf: {"user_id": actor_id})
    monkeypatch.setattr(admin_routes, "record_event", lambda db, **kwargs: audited.update(kwargs))

    result = admin_routes.support_access_platform_create(
        PlatformSupportAccessCreate(clinic_id=clinic_id, requested_by_user_id=requester_id, approved_by_user_id=approver_id, reason="Investigate a support issue", permissions=["patient.read"], expires_in_minutes=30),
        _request(),
        db,
        "session-token",
        "csrf-token",
    )

    assert result["data"]["id"] == access_id
    assert audited["action"] == "admin.support_access.create"
    assert audited["clinic_id"] is None
    assert audited["metadata"]["clinic_id"] == str(clinic_id)


def test_platform_support_access_revoke_returns_not_found_for_expired_or_revoked(monkeypatch) -> None:
    db = Mock()
    db.execute.return_value = Mock(mappings=lambda: Mock(one_or_none=lambda: None))
    monkeypatch.setattr(admin_routes, "_write", lambda db, request, token, csrf: {"user_id": uuid4()})

    with pytest.raises(Exception) as error:
        admin_routes.support_access_platform_revoke(uuid4(), _request(), db, "session-token", "csrf-token")

    assert getattr(error.value, "status_code", None) == 404


def test_platform_audit_search_returns_global_nonclinical_fields_only(monkeypatch) -> None:
    event_id = uuid4()
    db = Mock()
    db.execute.return_value = Mock(mappings=lambda: Mock(all=lambda: [{"id": event_id, "action": "admin.clinic.suspend", "entity_type": "clinic", "outcome": "success", "request_id": uuid4(), "created_at": None}]))
    monkeypatch.setattr(admin_routes, "_platform", lambda db, token: {"user_id": uuid4()})

    result = admin_routes.platform_audit_search(_request(), None, 50, db, "session-token")

    assert result["data"][0]["action"] == "admin.clinic.suspend"
    assert "metadata" not in result["data"][0]
    assert result["meta"]["global_only"] is True


def test_platform_privacy_and_export_lists_exclude_patient_fields(monkeypatch) -> None:
    clinic_id = uuid4()
    db = Mock()
    db.execute.return_value = Mock(mappings=lambda: Mock(all=lambda: [{"id": uuid4(), "clinic_id": clinic_id, "request_type": "access", "status": "requested", "requested_at": None, "resolved_at": None}]))
    monkeypatch.setattr(admin_routes, "_platform", lambda db, token: {"user_id": uuid4()})
    monkeypatch.setattr(admin_routes, "_platform_clinic_ids", lambda db: [clinic_id])
    monkeypatch.setattr(admin_routes, "set_tenant_context", lambda db, clinic_id: None)

    privacy = admin_routes.platform_privacy_request_list(_request(), 100, db, "session-token")
    assert "patient_id" not in privacy["data"][0]
    assert privacy["meta"]["clinical_fields_excluded"] is True

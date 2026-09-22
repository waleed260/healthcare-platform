from datetime import timedelta
from unittest.mock import Mock
from uuid import uuid4

from app.core.security import hash_token
from app.modules.identity.service import authenticate, create_manual_reset


def test_platform_user_requires_mfa_and_uses_short_session(monkeypatch):
    user_id = uuid4()
    db = Mock()
    db.execute.side_effect = [
        Mock(scalar_one_or_none=lambda: None),
        Mock(mappings=lambda: Mock(one_or_none=lambda: {
            "id": user_id,
            "clinic_id": None,
            "display_name": "Platform Operator",
            "password_hash": "stored",
            "status": "active",
        })),
        Mock(),
        Mock(mappings=lambda: Mock(one=lambda: {"mfa_enrolled": False, "mfa_mandatory": True})),
        Mock(),
        Mock(),
    ]
    monkeypatch.setattr("app.modules.identity.service.verify_password", lambda stored, supplied: True)
    monkeypatch.setattr("app.modules.identity.service.set_tenant_context", lambda db, clinic_id, user_id: None)
    monkeypatch.setattr("app.modules.identity.service.new_opaque_token", lambda: "t" * 64)
    monkeypatch.setattr("app.modules.identity.service.new_csrf_token", lambda: "c" * 32)

    result = authenticate(db, "operator@example.test", "StrongPassword1", "192.0.2.1", None)

    assert result.mfa_required is True
    assert result.mfa_enrollment_required is True
    session_params = db.execute.call_args_list[4].args[1]
    assert session_params["absolute_expires_at"] - session_params["idle_expires_at"] == timedelta(hours=23, minutes=30)


def test_clinic_owner_mfa_role_check_sets_context_before_forced_rls_query(monkeypatch):
    user_id = uuid4()
    clinic_id = uuid4()
    db = Mock()
    db.execute.side_effect = [
        Mock(scalar_one_or_none=lambda: None),
        Mock(mappings=lambda: Mock(one_or_none=lambda: {
            "id": user_id,
            "clinic_id": clinic_id,
            "display_name": "Synthetic Owner",
            "password_hash": "stored",
            "status": "active",
        })),
        Mock(),
        Mock(mappings=lambda: Mock(one=lambda: {"mfa_enrolled": False, "mfa_mandatory": True})),
        Mock(),
        Mock(),
    ]
    context = Mock()
    monkeypatch.setattr("app.modules.identity.service.set_tenant_context", context)
    monkeypatch.setattr("app.modules.identity.service.verify_password", lambda stored, supplied: True)
    monkeypatch.setattr("app.modules.identity.service.new_opaque_token", lambda: "t" * 64)
    monkeypatch.setattr("app.modules.identity.service.new_csrf_token", lambda: "c" * 32)

    result = authenticate(db, "owner@example.test", "StrongPassword1", "192.0.2.2", None)

    assert result.mfa_enrollment_required is True
    context.assert_called_once_with(db, clinic_id, user_id)


def test_manual_reset_persists_only_a_hashed_single_use_token(monkeypatch):
    user_id = uuid4()
    db = Mock()
    token = "r" * 64
    monkeypatch.setattr("app.modules.identity.service.new_opaque_token", lambda: token)

    assert create_manual_reset(db, user_id) == token
    lock_call, delete_call, insert_call = db.execute.call_args_list
    assert "pg_advisory_xact_lock" in str(lock_call.args[0])
    assert "DELETE FROM password_reset_tokens" in str(delete_call.args[0])
    params = insert_call.args[1]
    assert params["user_id"] == user_id
    assert params["token_hash"] == hash_token(token)
    assert params["token_hash"] != token

from datetime import timedelta
from unittest.mock import Mock
from uuid import uuid4

from app.modules.identity.service import authenticate


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
        Mock(scalar_one=lambda: True),
        Mock(),
        Mock(),
    ]
    monkeypatch.setattr("app.modules.identity.service.verify_password", lambda stored, supplied: True)
    monkeypatch.setattr("app.modules.identity.service.new_opaque_token", lambda: "t" * 64)
    monkeypatch.setattr("app.modules.identity.service.new_csrf_token", lambda: "c" * 32)

    result = authenticate(db, "operator@example.test", "StrongPassword1", "192.0.2.1", None)

    assert result.mfa_required is True
    session_params = db.execute.call_args_list[4].args[1]
    assert session_params["absolute_expires_at"] - session_params["idle_expires_at"] == timedelta(hours=23, minutes=30)

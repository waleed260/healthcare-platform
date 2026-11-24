"""MFA is opt-in for every role: _start_session never force-enrolls any role and
only requires MFA once the user has enrolled it. Mocks the db — no PostgreSQL needed."""
from unittest.mock import MagicMock
from uuid import uuid4

from app.modules.identity import service


def _start(*, is_platform_admin: bool, mfa_enrolled: bool, clinic_id=None):
    captured: dict = {}

    def execute(statement, params=None):
        sql = str(statement)
        if "mfa_enrolled" in sql:
            m = MagicMock()
            m.mappings.return_value.one.return_value = {"mfa_enrolled": mfa_enrolled}
            return m
        if "INSERT INTO sessions" in sql:
            captured["session"] = params
        return MagicMock()

    db = MagicMock()
    db.execute.side_effect = execute
    user = {
        "id": uuid4(), "clinic_id": clinic_id, "display_name": "T",
        "password_hash": "x", "status": "active", "is_platform_admin": is_platform_admin,
    }
    result = service._start_session(db, user, "1.2.3.4", "agent")
    return result, captured["session"]


def test_unenrolled_platform_admin_is_not_forced_into_mfa():
    # MFA is opt-in: an unenrolled platform admin logs straight into the workspace.
    result, session = _start(is_platform_admin=True, mfa_enrolled=False)
    assert result.mfa_required is False
    assert result.mfa_enrollment_required is False
    assert session["mfa_verified"] is True


def test_enrolled_platform_admin_must_verify_but_not_re_enroll():
    result, session = _start(is_platform_admin=True, mfa_enrolled=True)
    assert result.mfa_required is True
    assert result.mfa_enrollment_required is False
    assert session["mfa_verified"] is False


def test_clinic_user_without_mfa_is_unchanged():
    result, session = _start(is_platform_admin=False, mfa_enrolled=False, clinic_id=uuid4())
    assert result.mfa_required is False
    assert result.mfa_enrollment_required is False
    assert session["mfa_verified"] is True


def test_clinic_user_with_mfa_still_requires_verification():
    result, session = _start(is_platform_admin=False, mfa_enrolled=True, clinic_id=uuid4())
    assert result.mfa_required is True
    assert result.mfa_enrollment_required is False
    assert session["mfa_verified"] is False

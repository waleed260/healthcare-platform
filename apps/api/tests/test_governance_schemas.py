import pytest
from pydantic import ValidationError
from uuid import uuid4

from app.modules.governance.schemas import ClinicLifecycleUpdate, PlatformSupportAccessCreate, PrivacyRequestCreate, RetentionPolicyCreate, SupportAccessCreate


def test_support_access_requires_bounded_reason_and_duration() -> None:
    with pytest.raises(ValidationError):
        SupportAccessCreate(reason="short", permissions=["patient.read"], expires_in_minutes=61)


def test_privacy_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        PrivacyRequestCreate(request_type="access", reason="Patient request", internal_override=True)


def test_support_access_rejects_unknown_permission() -> None:
    with pytest.raises(ValidationError):
        SupportAccessCreate(reason="Investigate a support issue", permissions=["patient.delete"], expires_in_minutes=5)


def test_retention_policy_rules_are_bounded() -> None:
    policy = RetentionPolicyCreate(name="Synthetic policy", jurisdiction="Synthetic jurisdiction", rules={"documents": {"days": 365}})
    assert policy.rules["documents"]["days"] == 365
    with pytest.raises(ValidationError):
        RetentionPolicyCreate(name="Synthetic policy", jurisdiction="Synthetic jurisdiction", rules={"x": "a" * 16001})


def test_clinic_lifecycle_requires_reason_and_known_action() -> None:
    command = ClinicLifecycleUpdate(action="suspend", reason="Suspicious activity review", expected_version=3)
    assert command.expected_version == 3
    with pytest.raises(ValidationError):
        ClinicLifecycleUpdate(action="delete", reason="A sufficiently long reason", expected_version=3)
    with pytest.raises(ValidationError):
        ClinicLifecycleUpdate(action="suspend", reason="short", expected_version=3)


def test_platform_support_access_bounds_expiry_and_permissions() -> None:
    command = PlatformSupportAccessCreate(clinic_id=uuid4(), requested_by_user_id=uuid4(), approved_by_user_id=uuid4(), reason="Investigate a support issue", permissions=["patient.read"], expires_in_minutes=60)
    assert command.expires_in_minutes == 60
    with pytest.raises(ValidationError):
        PlatformSupportAccessCreate(clinic_id=uuid4(), requested_by_user_id=uuid4(), approved_by_user_id=uuid4(), reason="Investigate a support issue", permissions=["patient.read"], expires_in_minutes=61)

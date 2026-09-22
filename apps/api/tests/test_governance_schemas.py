import pytest
from pydantic import ValidationError

from app.modules.governance.schemas import PrivacyRequestCreate, RetentionPolicyCreate, SupportAccessCreate


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

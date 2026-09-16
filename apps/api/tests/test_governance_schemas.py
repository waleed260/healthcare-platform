import pytest
from pydantic import ValidationError

from app.modules.governance.schemas import PrivacyRequestCreate, SupportAccessCreate


def test_support_access_requires_bounded_reason_and_duration() -> None:
    with pytest.raises(ValidationError):
        SupportAccessCreate(reason="short", permissions=["patient.read"], expires_in_minutes=61)


def test_privacy_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        PrivacyRequestCreate(request_type="access", reason="Patient request", internal_override=True)


def test_support_access_rejects_unknown_permission() -> None:
    with pytest.raises(ValidationError):
        SupportAccessCreate(reason="Investigate a support issue", permissions=["patient.delete"], expires_in_minutes=5)

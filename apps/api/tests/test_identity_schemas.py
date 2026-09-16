import pytest
from pydantic import ValidationError

from app.modules.identity.schemas import InvitationConsumeRequest


def test_invitation_consume_requires_display_name() -> None:
    request = InvitationConsumeRequest(token="t" * 32, password="Synthetic-password-123", display_name="Synthetic Staff")
    assert request.display_name == "Synthetic Staff"

    with pytest.raises(ValidationError):
        InvitationConsumeRequest(token="t" * 32, password="Synthetic-password-123")

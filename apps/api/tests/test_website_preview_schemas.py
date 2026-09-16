import pytest
from pydantic import ValidationError

from app.modules.websites.schemas import DomainCreate


def test_preview_domain_schema_rejects_protocol_hosts() -> None:
    with pytest.raises(ValidationError):
        DomainCreate(hostname="https://example.test")

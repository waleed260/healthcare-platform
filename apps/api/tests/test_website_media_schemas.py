import pytest
from pydantic import ValidationError

from app.modules.websites.schemas import DomainCreate, WebsiteLeadCreate, WebsiteMediaCreate


def test_website_media_allows_only_safe_image_types() -> None:
    with pytest.raises(ValidationError):
        WebsiteMediaCreate(original_filename="payload.svg", alt_text="Synthetic logo", mime_type="image/svg+xml")


def test_domain_requires_a_bounded_hostname() -> None:
    with pytest.raises(ValidationError):
        DomainCreate(hostname="x" * 254)


def test_public_lead_requires_explicit_consent() -> None:
    with pytest.raises(ValidationError):
        WebsiteLeadCreate(full_name="Amina", consent="yes")

    lead = WebsiteLeadCreate(full_name="Amina", consent=True)
    assert lead.full_name == "Amina"

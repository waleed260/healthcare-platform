import pytest
from pydantic import ValidationError

from app.main import app
from app.modules.website_library.schemas import PageFromTemplate, ReusableInsert
from app.modules.website_library.templates import PAGE_TEMPLATES, SITE_TEMPLATES
from app.modules.websites.publishing import REQUIRED_LEGAL_SLUGS
from app.modules.websites.schemas import WebsiteSectionUpdate
from app.modules.websites.sanitizer import validate_navigation_href
from app.modules.websites.theme import normalize_brand


@pytest.mark.parametrize("template", SITE_TEMPLATES, ids=lambda t: t["key"])
def test_site_templates_are_publishable_and_valid(template: dict) -> None:
    slugs = {page["slug"] for page in template["pages"]}
    assert REQUIRED_LEGAL_SLUGS <= slugs and "home" in slugs
    normalize_brand({key: template[key] for key in ("theme", "header", "footer")})
    for page in template["pages"]:
        positions = set()
        for position, section in enumerate(page["sections"]):
            WebsiteSectionUpdate(position=position, **section)
            validate_navigation_href(section["content"].get("button_href"))
            positions.add(position)
        assert len(positions) == len(page["sections"])


def test_page_templates_are_valid() -> None:
    assert {t["key"] for t in PAGE_TEMPLATES} >= {"service_page", "doctor_page", "location_page"}
    for template in PAGE_TEMPLATES:
        for position, section in enumerate(template["sections"]):
            WebsiteSectionUpdate(position=position, **section)


def test_schema_guards() -> None:
    with pytest.raises(ValidationError):
        PageFromTemplate(template_key="service_page", slug="Bad Slug", title="x")
    with pytest.raises(ValidationError):
        ReusableInsert(mode="linked")
    assert "/api/v1/website-library/templates" in app.openapi()["paths"]

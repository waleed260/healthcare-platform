import pytest
from pydantic import ValidationError

from app.main import app
from app.modules.websites.schemas import RedirectCreate, WebsitePageCreate, WebsitePageUpdate
from app.modules.websites.theme import normalize_brand


def test_page_seo_fields_validate() -> None:
    page = WebsitePageCreate(slug="about", title="About", canonical_url="https://clinic.example/about", noindex=True, og_title="About us")
    assert page.noindex is True
    assert WebsitePageUpdate(expected_version=1, canonical_url="").canonical_url is None
    with pytest.raises(ValidationError):
        WebsitePageCreate(slug="x", title="x", canonical_url="javascript:alert(1)")


def test_redirect_rules() -> None:
    assert RedirectCreate(from_path="/old-page/", to_path="/new-page").from_path == "/old-page"
    assert RedirectCreate(from_path="/a", to_path="https://example.com/b", status_code=302).status_code == 302
    for bad in ({"from_path": "no-slash", "to_path": "/x"}, {"from_path": "/a b", "to_path": "/x"}, {"from_path": "/a", "to_path": "javascript:x"}, {"from_path": "/a", "to_path": "/x", "status_code": 307}):
        with pytest.raises(ValidationError):
            RedirectCreate(**bad)


def test_brand_seo_settings() -> None:
    brand = normalize_brand({"seo": {"robots_index": False, "disallow_paths": ["/private/*"], "site_name": "Smile"}})
    assert brand["seo"]["robots_index"] is False
    with pytest.raises(ValidationError):
        normalize_brand({"seo": {"disallow_paths": ["no-slash"]}})
    with pytest.raises(ValidationError):
        normalize_brand({"seo": {"disallow_paths": ["/x\nSitemap: https://evil"]}})


def test_redirect_routes_registered() -> None:
    assert "/api/v1/websites/{website_id}/redirects" in app.openapi()["paths"]

import pytest
from pydantic import ValidationError

from app.modules.websites.schemas import WebsiteCreate, WebsiteUpdate
from app.modules.websites.theme import normalize_brand


def test_legacy_flat_brand_still_validates() -> None:
    brand = normalize_brand({"primary_color": "#274c42", "background_color": "#f5f4ee"})
    assert brand == {"primary_color": "#274c42", "background_color": "#f5f4ee"}


def test_theme_header_footer_roundtrip_with_defaults() -> None:
    brand = normalize_brand({
        "theme": {"colors": {"primary": "#112233"}, "buttons": {"style": "outline", "radius": 8}},
        "header": {"nav": [{"label": "Services", "href": "#services", "children": [{"label": "Dental", "href": "/services/dental"}]}], "phone": "+92 300 1234567", "social": {"instagram": "https://instagram.com/clinic"}},
        "footer": {"columns": [{"kind": "hours"}, {"kind": "contact", "title": "Visit us"}]},
        "mobile": {"font_scale": 0.9, "hide_section_ids": ["abc"]},
    })
    assert brand["theme"]["buttons"]["radius"] == 8 and brand["theme"]["typography"]["h1_size"] == 56
    assert brand["header"]["nav"][0]["children"][0]["label"] == "Dental"


@pytest.mark.parametrize("bad", [
    {"theme": {"colors": {"primary": "red"}}},
    {"header": {"nav": [{"label": "x", "href": "javascript:alert(1)"}]}},
    {"header": {"social": {"instagram": "http://insecure"}}},
    {"header": {"phone": "<script>"}},
    {"theme": {"layout": {"container_width": 99999}}},
    {"unknown_key": 1},
])
def test_unsafe_or_out_of_range_brand_is_rejected(bad: dict) -> None:
    with pytest.raises(ValidationError):
        WebsiteCreate(name="Site", template_key="calm_clinic", brand=bad)


def test_update_accepts_none_and_validates_brand() -> None:
    assert WebsiteUpdate(expected_version=1, name="x").brand is None
    with pytest.raises(ValidationError):
        WebsiteUpdate(expected_version=1, brand={"theme": {"colors": {"text": "#12"}}})


def test_publish_contrast_checks_theme_colors() -> None:
    from app.modules.websites.publishing import validate_snapshot_contrast

    validate_snapshot_contrast({"brand": {"theme": {"colors": {"text": "#111111", "background": "#ffffff"}}}})
    with pytest.raises(ValueError):
        validate_snapshot_contrast({"brand": {"theme": {"colors": {"text": "#cccccc", "background": "#ffffff"}}}})

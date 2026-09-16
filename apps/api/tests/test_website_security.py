import pytest

from app.modules.websites.sanitizer import sanitize_rich_text, validate_navigation_href
from app.modules.websites.schemas import WebsiteCreate, WebsitePageCreate


def test_rich_text_sanitizer_removes_scripts_and_keeps_safe_markup() -> None:
    sanitized = sanitize_rich_text('<script>alert(1)</script><p><strong>Safe</strong> <a href="https://example.test">link</a></p>')
    assert "script" not in sanitized.lower()
    assert "alert" not in sanitized.lower()
    assert "<strong>Safe</strong>" in sanitized
    assert 'href="https://example.test"' in sanitized


def test_rich_text_sanitizer_removes_javascript_urls() -> None:
    assert "javascript:" not in sanitize_rich_text('<a href="javascript:alert(1)">bad</a>').lower()


def test_structured_navigation_rejects_script_and_protocol_relative_urls() -> None:
    assert validate_navigation_href("/book") == "/book"
    assert validate_navigation_href("https://example.test/book") == "https://example.test/book"
    with pytest.raises(ValueError):
        validate_navigation_href("javascript:alert(1)")
    with pytest.raises(ValueError):
        validate_navigation_href("//evil.example/book")


def test_website_content_contract_is_strict_and_slug_is_normalized() -> None:
    assert WebsiteCreate(name="Synthetic Site", template_key="calm_clinic").template_key == "calm_clinic"
    assert WebsitePageCreate(slug="/Home/", title="Synthetic Home").slug == "home"
    with pytest.raises(ValueError):
        WebsitePageCreate(slug="javascript:bad", title="Synthetic")

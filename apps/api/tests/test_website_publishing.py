import pytest

from app.modules.websites.publishing import REQUIRED_LEGAL_SLUGS, snapshot_checksum, validate_publish_snapshot, validate_snapshot_contrast


def test_publish_requires_all_legal_pages() -> None:
    with pytest.raises(ValueError):
        validate_publish_snapshot({"pages": [{"slug": "home"}]})
    validate_publish_snapshot({"pages": [{"slug": slug} for slug in REQUIRED_LEGAL_SLUGS]})


def test_snapshot_checksum_is_stable_for_key_order() -> None:
    assert snapshot_checksum({"b": 2, "a": 1}) == snapshot_checksum({"a": 1, "b": 2})


def test_publish_rejects_inaccessible_configured_brand_contrast() -> None:
    with pytest.raises(ValueError, match="below WCAG AA"):
        validate_snapshot_contrast({"brand": {"text_color": "#777777", "background_color": "#ffffff"}})
    validate_snapshot_contrast({"brand": {"text_color": "#000000", "background_color": "#ffffff"}})

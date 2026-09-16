from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


REQUIRED_LEGAL_SLUGS = {"privacy", "cancellation", "medical-disclaimer"}
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _relative_luminance(hex_color: str) -> float:
    channels = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def validate_snapshot_contrast(snapshot: Mapping[str, object]) -> None:
    """Reject configured text/background pairs below WCAG AA normal-text contrast."""
    brand = snapshot.get("brand")
    if not isinstance(brand, Mapping):
        return
    pairs = (("text_color", "background_color"), ("foreground", "background"), ("primary_color", "background_color"))
    for foreground_key, background_key in pairs:
        foreground, background = brand.get(foreground_key), brand.get(background_key)
        if foreground is None or background is None:
            continue
        if not isinstance(foreground, str) or not isinstance(background, str) or not HEX_COLOR.fullmatch(foreground) or not HEX_COLOR.fullmatch(background):
            raise ValueError("brand colors must be six-digit hexadecimal values")
        ratio = (max(_relative_luminance(foreground), _relative_luminance(background)) + 0.05) / (min(_relative_luminance(foreground), _relative_luminance(background)) + 0.05)
        if ratio < 4.5:
            raise ValueError(f"brand contrast between {foreground_key} and {background_key} is below WCAG AA")


def validate_publish_snapshot(snapshot: Mapping[str, object]) -> None:
    pages = snapshot.get("pages")
    if not isinstance(pages, list):
        raise ValueError("snapshot must contain pages")
    slugs = {str(page.get("slug", "")).strip().casefold() for page in pages if isinstance(page, Mapping)}
    missing = REQUIRED_LEGAL_SLUGS - slugs
    if missing:
        raise ValueError("required legal pages are missing")
    validate_snapshot_contrast(snapshot)


def snapshot_checksum(snapshot: Mapping[str, object]) -> str:
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def build_draft_snapshot(db: Session, clinic_id: UUID, website_id: UUID) -> dict[str, object]:
    website = db.execute(text("SELECT template_key, brand FROM websites WHERE clinic_id = :clinic_id AND id = :website_id AND archived_at IS NULL"), {"clinic_id": clinic_id, "website_id": website_id}).mappings().one_or_none()
    if website is None:
        raise ValueError("website not found")
    pages = db.execute(text("SELECT id, slug, title, seo_title, seo_description FROM website_pages WHERE clinic_id = :clinic_id AND website_id = :website_id ORDER BY slug, id"), {"clinic_id": clinic_id, "website_id": website_id}).mappings().all()
    sections = db.execute(text("SELECT page_id, section_type, layout_key, position, content, is_visible FROM website_sections WHERE clinic_id = :clinic_id AND page_id = ANY(:page_ids) ORDER BY position, id"), {"clinic_id": clinic_id, "page_ids": [page["id"] for page in pages]}).mappings().all() if pages else []
    by_page: dict[object, list[dict[str, object]]] = {page["id"]: [] for page in pages}
    for section in sections:
        by_page[section["page_id"]].append({"section_type": section["section_type"], "layout_key": section["layout_key"], "position": section["position"], "content": section["content"], "is_visible": section["is_visible"]})
    return {"template_key": website["template_key"], "brand": website["brand"], "pages": [{"slug": page["slug"], "title": page["title"], "seo_title": page["seo_title"], "seo_description": page["seo_description"], "sections": by_page[page["id"]]} for page in pages]}


def refresh_draft_snapshot(db: Session, clinic_id: UUID, website_id: UUID, created_by: UUID) -> dict:
    snapshot = build_draft_snapshot(db, clinic_id, website_id)
    next_number = db.execute(text("SELECT COALESCE(MAX(version_number), 0) + 1 FROM website_versions WHERE clinic_id = :clinic_id AND website_id = :website_id"), {"clinic_id": clinic_id, "website_id": website_id}).scalar_one()
    version = db.execute(text("""
        INSERT INTO website_versions (clinic_id, website_id, version_number, schema_version, snapshot, checksum, created_by)
        VALUES (:clinic_id, :website_id, :version_number, 1, CAST(:snapshot AS jsonb), :checksum, :created_by)
        RETURNING id, version_number, checksum
    """), {"clinic_id": clinic_id, "website_id": website_id, "version_number": next_number, "snapshot": json.dumps(snapshot, default=str), "checksum": snapshot_checksum(snapshot), "created_by": created_by}).mappings().one()
    db.execute(text("UPDATE websites SET draft_version_id = :version_id, version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :website_id"), {"clinic_id": clinic_id, "website_id": website_id, "version_id": version["id"]})
    return {"snapshot": snapshot, **dict(version)}

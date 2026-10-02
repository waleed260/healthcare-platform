"""Validated theme, header and footer settings stored inside a website's ``brand`` document (blueprint §16)."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
SAFE_HREF = re.compile(r"^(/[A-Za-z0-9\-._~/?#=&%]*|#[A-Za-z0-9\-_]+|https://[^\s<>\"']+|tel:\+?[0-9 ()\-]{3,30}|mailto:[^\s<>\"']+)$")
FONTS = ("system", "serif", "sans", "humanist", "mono")


def _hex(value: str | None) -> str | None:
    if value is not None and not HEX.fullmatch(value):
        raise ValueError("colors must be six-digit hexadecimal values")
    return value


def _href(value: str | None) -> str | None:
    if value is not None and not SAFE_HREF.fullmatch(value):
        raise ValueError("links must be relative, anchors, https, tel or mailto")
    return value


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ThemeColors(_Strict):
    primary: str | None = None
    secondary: str | None = None
    accent: str | None = None
    background: str | None = None
    text: str | None = None
    muted: str | None = None
    border: str | None = None
    success: str | None = None
    error: str | None = None

    _check = field_validator("primary", "secondary", "accent", "background", "text", "muted", "border", "success", "error")(lambda cls, v: _hex(v))


class ThemeTypography(_Strict):
    heading_font: Literal["system", "serif", "sans", "humanist", "mono"] = "serif"
    body_font: Literal["system", "serif", "sans", "humanist", "mono"] = "sans"
    button_font: Literal["system", "serif", "sans", "humanist", "mono"] = "sans"
    h1_size: int = Field(default=56, ge=28, le=96)
    h2_size: int = Field(default=36, ge=20, le=64)
    body_size: int = Field(default=16, ge=13, le=22)
    heading_weight: int = Field(default=500, ge=300, le=800, multiple_of=100)
    line_height: float = Field(default=1.6, ge=1.2, le=2.2)


class ThemeButtons(_Strict):
    style: Literal["solid", "outline"] = "solid"
    radius: int = Field(default=2, ge=0, le=40)
    height: int = Field(default=44, ge=32, le=64)
    padding_x: int = Field(default=22, ge=8, le=48)


class ThemeLayout(_Strict):
    container_width: int = Field(default=1120, ge=720, le=1600)
    section_spacing: int = Field(default=72, ge=16, le=200)
    card_radius: int = Field(default=4, ge=0, le=40)
    shadow: Literal["none", "soft", "strong"] = "soft"
    gutter: int = Field(default=24, ge=8, le=64)


class ThemeForms(_Strict):
    input_style: Literal["boxed", "underline", "filled"] = "boxed"
    label_position: Literal["above", "floating"] = "above"
    field_spacing: int = Field(default=14, ge=6, le=40)


class ThemeSettings(_Strict):
    colors: ThemeColors = Field(default_factory=ThemeColors)
    typography: ThemeTypography = Field(default_factory=ThemeTypography)
    buttons: ThemeButtons = Field(default_factory=ThemeButtons)
    layout: ThemeLayout = Field(default_factory=ThemeLayout)
    forms: ThemeForms = Field(default_factory=ThemeForms)


class NavLink(_Strict):
    label: str = Field(min_length=1, max_length=60)
    href: str = Field(max_length=500)
    children: list["NavLink"] = Field(default_factory=list, max_length=12)

    _href = field_validator("href")(lambda cls, v: _href(v))


class HeaderSettings(_Strict):
    nav: list[NavLink] = Field(default_factory=list, max_length=12)
    sticky: bool = True
    transparent: bool = False
    show_book_cta: bool = True
    book_cta_label: str = Field(default="Book appointment", min_length=1, max_length=40)
    phone: str | None = Field(default=None, max_length=40, pattern=r"^\+?[0-9 ()\-]{3,40}$")
    announcement: str | None = Field(default=None, max_length=200)
    top_strip: bool = False
    social: dict[Literal["facebook", "instagram", "x", "linkedin", "youtube", "tiktok"], str] = Field(default_factory=dict)
    mobile_layout: Literal["drawer", "stacked", "compact"] = "drawer"

    @field_validator("social")
    @classmethod
    def social_links(cls, value: dict[str, str]) -> dict[str, str]:
        for link in value.values():
            if not link.startswith("https://") or len(link) > 300 or not SAFE_HREF.fullmatch(link):
                raise ValueError("social links must be https URLs")
        return value


class FooterColumn(_Strict):
    kind: Literal["about", "services", "quick_links", "branches", "hours", "contact", "social", "legal", "custom"]
    title: str = Field(default="", max_length=80)
    body: str = Field(default="", max_length=600)
    links: list[NavLink] = Field(default_factory=list, max_length=12)


class FooterSettings(_Strict):
    columns: list[FooterColumn] = Field(default_factory=list, max_length=6)
    copyright: str = Field(default="", max_length=200)
    show_legal_links: bool = True


class DeviceOverrides(_Strict):
    """Per-device tweaks (blueprint §16.4): font scale, spacing and hidden blocks."""

    font_scale: float = Field(default=1.0, ge=0.7, le=1.4)
    spacing_scale: float = Field(default=1.0, ge=0.5, le=1.5)
    hide_section_ids: list[str] = Field(default_factory=list, max_length=50)
    hero_mobile_media_id: str | None = Field(default=None, pattern=r"^[0-9a-fA-F-]{36}$")


class BrandDocument(BaseModel):
    """Known brand keys are validated; legacy flat color keys keep working."""

    model_config = ConfigDict(extra="forbid")

    logo_media_id: str | None = Field(default=None, pattern=r"^[0-9a-fA-F-]{36}$")
    primary_color: str | None = None
    accent_color: str | None = None
    text_color: str | None = None
    background_color: str | None = None
    font_pairing: str | None = Field(default=None, max_length=60)
    theme: ThemeSettings | None = None
    header: HeaderSettings | None = None
    footer: FooterSettings | None = None
    tablet: DeviceOverrides | None = None
    mobile: DeviceOverrides | None = None

    _colors = field_validator("primary_color", "accent_color", "text_color", "background_color")(lambda cls, v: _hex(v))


def normalize_brand(value: dict[str, object]) -> dict[str, object]:
    """Validate and return the brand document without dropping defaults the editor set."""
    return BrandDocument.model_validate(value).model_dump(mode="json", exclude_none=True)

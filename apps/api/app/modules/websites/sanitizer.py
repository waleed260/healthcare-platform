import bleach
import re
from urllib.parse import urlparse


ALLOWED_TAGS = {"p", "br", "strong", "em", "ul", "ol", "li", "a"}
ALLOWED_ATTRIBUTES = {"a": ["href", "title", "rel"]}


def sanitize_rich_text(value: str) -> str:
    value = re.sub(r"<\s*(script|style)(?:\s[^>]*)?>.*?<\s*/\s*\1\s*>", "", value, flags=re.IGNORECASE | re.DOTALL)
    return bleach.clean(value, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, protocols={"http", "https"}, strip=True)


def validate_navigation_href(value: str | None) -> str | None:
    """Allow only safe web navigation targets in structured section content."""
    if value is None:
        return None
    candidate = value.strip()
    if not candidate or "\x00" in candidate:
        raise ValueError("navigation target is invalid")
    parsed = urlparse(candidate)
    if candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return candidate
    raise ValueError("navigation target must be an https/http URL or relative path")

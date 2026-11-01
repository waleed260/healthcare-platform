from __future__ import annotations

import re
from collections.abc import Iterable

_COLUMN_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def assert_safe_columns(fields: Iterable[str], allowed: frozenset[str]) -> None:
    for f in fields:
        if f not in allowed or not _COLUMN_RE.match(f):
            raise ValueError(f"Disallowed column: {f}")

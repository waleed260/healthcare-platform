"""Every permission the DB registers must be in the PERMISSIONS allowlist (require_permission rejects unknowns).

clinical.form.* and patient.media.* were registered by migrations but missing from the allowlist, so those
endpoints raised 'unknown permission code' (HTTP 500). This keeps the two sources in sync.
"""
import os
import re
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.modules.authorization.permissions import PERMISSIONS

pytestmark = pytest.mark.integration
MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"


def _registered_in_migrations() -> set[str]:
    codes: set[str] = set()
    for path in MIGRATIONS.glob("*.py"):
        text_body = path.read_text()
        # INSERT INTO permissions ... ('code', 'desc')
        for m in re.finditer(r"\(\s*'([a-z][a-z0-9_.]+)'\s*,\s*'[^']*'\s*\)", text_body):
            code = m.group(1)
            if "." in code and code.split(".")[0] in {"clinic", "branch", "staff", "doctor", "service", "schedule", "appointment", "queue", "patient", "consent", "followup", "notification", "website", "audit", "admin", "specialty", "lead", "billing", "clinical", "report", "package", "inventory", "expense"}:
                codes.add(code)
    return codes


def test_migration_permissions_are_in_allowlist() -> None:
    missing = sorted(_registered_in_migrations() - PERMISSIONS)
    assert not missing, f"permission codes registered by migrations but absent from PERMISSIONS: {missing}"


def test_db_permissions_match_allowlist() -> None:
    url = os.getenv("TEST_ADMIN_DATABASE_URL") or os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("no database configured")
    with create_engine(url).connect() as conn:
        db_codes = {row[0] for row in conn.execute(text("SELECT code FROM permissions"))}
    missing = sorted(db_codes - PERMISSIONS)
    assert not missing, f"permission codes in DB but not in PERMISSIONS: {missing}"

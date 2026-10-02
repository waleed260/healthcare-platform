"""Platform-admin sessions leave app.clinic_id empty; tenant policies must not cast '' to uuid.

Regression for the crash that broke /api/v1/admin/overview and /admin/upgrade-requests:
a tenant policy using current_setting('app.clinic_id',true)::uuid raised invalid-input-syntax
for an empty string. Guarded here (live) and by a static check of the policy catalogue.
"""
import os

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration


def _runtime_engine():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("PostgreSQL integration URL is not configured")
    return create_engine(url)


def test_no_tenant_policy_casts_empty_clinic_id() -> None:
    engine = _runtime_engine()
    with engine.connect() as conn:
        offenders = conn.execute(text(
            "SELECT tablename, policyname FROM pg_policies "
            "WHERE schemaname='public' AND policyname LIKE '%_tenant_policy' "
            "AND qual LIKE '%app.clinic_id%' AND qual NOT LIKE '%NULLIF%'"
        )).fetchall()
    assert not offenders, f"tenant policies that cast an unguarded clinic_id: {offenders}"


def test_platform_admin_context_can_query_tenant_tables() -> None:
    engine = _runtime_engine()
    with engine.connect() as conn:
        # Reproduce a platform-admin session: empty clinic, is_platform_admin=true.
        conn.execute(text("SELECT set_config('app.clinic_id', '', true), set_config('app.is_platform_admin', 'true', true)"))
        # upgrade_requests (has the platform escape) and a plain tenant table must both be queryable.
        assert conn.execute(text("SELECT count(*) FROM upgrade_requests")).scalar_one() is not None
        assert conn.execute(text("SELECT count(*) FROM invoices")).scalar_one() is not None

"""Production-snapshot regression tests for theme_instances row-level security."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from app.db.tenant import set_tenant_context


pytestmark = pytest.mark.integration


def _database_urls() -> tuple[str, str]:
    admin_url = os.getenv("TEST_ADMIN_DATABASE_URL")
    runtime_url = os.getenv("TEST_DATABASE_URL")
    if not admin_url or not runtime_url:
        pytest.skip("PostgreSQL admin/runtime integration URLs are not configured")
    return admin_url, runtime_url


@pytest.fixture
def theme_tenant_records() -> dict[str, object]:
    """Seed two synthetic clinics and their websites/theme rows as the admin role."""
    admin_url, runtime_url = _database_urls()
    admin = create_engine(admin_url)
    runtime = create_engine(runtime_url, poolclass=NullPool)

    clinic_a, clinic_b = uuid4(), uuid4()
    website_a, website_b = uuid4(), uuid4()
    theme_a, theme_b = uuid4(), uuid4()

    try:
        with admin.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO clinics (id, name, slug)
                    VALUES (:a, 'Theme RLS A', :slug_a), (:b, 'Theme RLS B', :slug_b)
                    """
                ),
                {
                    "a": clinic_a,
                    "b": clinic_b,
                    "slug_a": f"theme-rls-a-{clinic_a}",
                    "slug_b": f"theme-rls-b-{clinic_b}",
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO websites (id, clinic_id, name, template_key)
                    VALUES
                        (:website_a, :clinic_a, 'Theme RLS Website A', 'calm_clinic'),
                        (:website_b, :clinic_b, 'Theme RLS Website B', 'calm_clinic')
                    """
                ),
                {
                    "website_a": website_a,
                    "clinic_a": clinic_a,
                    "website_b": website_b,
                    "clinic_b": clinic_b,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO theme_instances (id, clinic_id, website_id, name)
                    VALUES
                        (:theme_a, :clinic_a, :website_a, 'Theme A'),
                        (:theme_b, :clinic_b, :website_b, 'Theme B')
                    """
                ),
                {
                    "theme_a": theme_a,
                    "clinic_a": clinic_a,
                    "website_a": website_a,
                    "theme_b": theme_b,
                    "clinic_b": clinic_b,
                    "website_b": website_b,
                },
            )

        yield {
            "admin": admin,
            "runtime": runtime,
            "clinic_a": clinic_a,
            "clinic_b": clinic_b,
            "website_a": website_a,
            "website_b": website_b,
            "theme_a": theme_a,
            "theme_b": theme_b,
        }
    finally:
        # The synthetic clinics own the websites and theme rows; FK cascades
        # remove those records without touching pre-existing clinic data.
        with admin.begin() as connection:
            connection.execute(
                text("DELETE FROM clinics WHERE id IN (:a, :b)"),
                {"a": clinic_a, "b": clinic_b},
            )
        runtime.dispose()
        admin.dispose()


def test_theme_instances_policy_preserves_metadata_and_guards_both_expressions(
    theme_tenant_records: dict[str, object],
) -> None:
    runtime: Engine = theme_tenant_records["runtime"]  # type: ignore[assignment]

    with runtime.connect() as connection:
        role = connection.execute(
            text(
                """
                SELECT rolname, rolsuper, rolbypassrls
                FROM pg_roles
                WHERE rolname = current_user
                """
            )
        ).mappings().one()
        assert role["rolname"] == "healthcare_runtime"
        assert role["rolsuper"] is False
        assert role["rolbypassrls"] is False

        table = connection.execute(
            text(
                """
                SELECT relrowsecurity, relforcerowsecurity
                FROM pg_class
                WHERE oid = to_regclass('public.theme_instances')
                """
            )
        ).mappings().one()
        assert table["relrowsecurity"] is True
        assert table["relforcerowsecurity"] is True

        policy = connection.execute(
            text(
                """
                SELECT permissive, roles, cmd, qual, with_check
                FROM pg_policies
                WHERE schemaname = 'public'
                  AND tablename = 'theme_instances'
                  AND policyname = 'theme_instances_tenant_policy'
                """
            )
        ).mappings().one()
        assert policy["permissive"] == "PERMISSIVE"
        assert set(policy["roles"]) == {"public"}
        assert policy["cmd"] == "ALL"
        assert "NULLIF" in policy["qual"].upper()
        assert "NULLIF" in policy["with_check"].upper()


def test_theme_instances_empty_and_missing_context_fail_closed_without_cast_error(
    theme_tenant_records: dict[str, object],
) -> None:
    runtime: Engine = theme_tenant_records["runtime"]  # type: ignore[assignment]

    # NullPool guarantees a fresh PostgreSQL session, so this transaction starts
    # without a previously configured app.clinic_id custom GUC.
    with runtime.connect() as connection:
        with connection.begin():
            current_clinic = connection.execute(
                text("SELECT current_setting('app.clinic_id', true)")
            ).scalar_one_or_none()
            assert current_clinic in (None, "")
            visible = connection.execute(
                text("SELECT id FROM theme_instances ORDER BY id")
            ).scalars().all()
            assert visible == []

    # Platform-admin and other no-tenant paths commonly set the custom GUC to ''.
    # The real runtime role must see no rows and must not raise PostgreSQL 22P02.
    with runtime.begin() as connection:
        connection.execute(
            text("SELECT set_config('app.clinic_id', '', true)")
        )
        visible = connection.execute(
            text("SELECT id FROM theme_instances ORDER BY id")
        ).scalars().all()
        assert visible == []


def test_theme_instances_runtime_role_enforces_read_and_write_tenant_isolation(
    theme_tenant_records: dict[str, object],
) -> None:
    runtime: Engine = theme_tenant_records["runtime"]  # type: ignore[assignment]
    clinic_a = theme_tenant_records["clinic_a"]
    clinic_b = theme_tenant_records["clinic_b"]
    website_b = theme_tenant_records["website_b"]
    theme_a = theme_tenant_records["theme_a"]
    theme_b = theme_tenant_records["theme_b"]

    with runtime.begin() as connection:
        set_tenant_context(connection, clinic_a)  # type: ignore[arg-type]
        visible = connection.execute(
            text("SELECT id FROM theme_instances ORDER BY id")
        ).scalars().all()
        assert visible == [theme_a]

        # A cross-tenant UPDATE is filtered by USING and cannot modify Clinic B.
        result = connection.execute(
            text("UPDATE theme_instances SET name = 'tampered' WHERE id = :theme_b"),
            {"theme_b": theme_b},
        )
        assert result.rowcount == 0

    # WITH CHECK must reject inserting a row owned by another clinic.
    with runtime.begin() as connection:
        set_tenant_context(connection, clinic_a)  # type: ignore[arg-type]
        with pytest.raises(DBAPIError):
            with connection.begin_nested():
                connection.execute(
                    text(
                        """
                        INSERT INTO theme_instances (id, clinic_id, website_id, name)
                        VALUES (:id, :clinic_b, :website_b, 'forbidden insert')
                        """
                    ),
                    {
                        "id": uuid4(),
                        "clinic_b": clinic_b,
                        "website_b": website_b,
                    },
                )

    # WITH CHECK must also reject changing an owned row to another tenant.
    with runtime.begin() as connection:
        set_tenant_context(connection, clinic_a)  # type: ignore[arg-type]
        with pytest.raises(DBAPIError):
            with connection.begin_nested():
                connection.execute(
                    text(
                        """
                        UPDATE theme_instances
                        SET clinic_id = :clinic_b, website_id = :website_b
                        WHERE id = :theme_a
                        """
                    ),
                    {
                        "clinic_b": clinic_b,
                        "website_b": website_b,
                        "theme_a": theme_a,
                    },
                )

    # Symmetric read isolation: Clinic B sees only its own theme instance.
    with runtime.begin() as connection:
        set_tenant_context(connection, clinic_b)  # type: ignore[arg-type]
        visible = connection.execute(
            text("SELECT id FROM theme_instances ORDER BY id")
        ).scalars().all()
        assert visible == [theme_b]

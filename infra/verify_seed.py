"""Verify the deterministic demo seed through admin and runtime connections.

The seed is written with the migration/admin connection, then read with the
restricted runtime role under an explicit clinic context. This is deliberately
an infrastructure check rather than an application endpoint.
"""

from __future__ import annotations

import os
from uuid import UUID, uuid5

import psycopg


NAMESPACE = UUID("a59c4f7e-97c1-4c14-9a2e-0f30f5c63d8b")
CLINIC_A = uuid5(NAMESPACE, "clinic-a")
CLINIC_B = uuid5(NAMESPACE, "clinic-b")


def url(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is required")
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def count(connection: psycopg.Connection, table: str, clinic_id: UUID) -> int:
    column = "id" if table == "clinics" else "clinic_id"
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT count(*) FROM {table} WHERE {column} = %s", (clinic_id,))
        return int(cursor.fetchone()[0])


def main() -> None:
    admin_url = url("SEED_DATABASE_URL")
    runtime_url = url("TEST_DATABASE_URL")
    expected = {
        "clinics": 1,
        "branches": 1,
        "services": 1,
        "doctor_profiles": 1,
        "patients": 4,
        "appointments": 4,
        "queue_entries": 2,
        "follow_up_tasks": 3,
        "notifications": 1,
    }

    with psycopg.connect(admin_url) as admin:
        with admin.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM clinics WHERE id IN (%s, %s)", (CLINIC_A, CLINIC_B))
            assert cursor.fetchone()[0] == 2, "both deterministic clinics must exist"
            for clinic_id in (CLINIC_A, CLINIC_B):
                for table, expected_count in expected.items():
                    actual = count(admin, table, clinic_id)
                    assert actual == expected_count, f"{table} for {clinic_id}: expected {expected_count}, got {actual}"

    with psycopg.connect(runtime_url) as runtime:
        with runtime.cursor() as cursor:
            cursor.execute("SELECT set_config('app.clinic_id', %s, true)", (str(CLINIC_A),))
            for table, expected_count in expected.items():
                actual = count(runtime, table, CLINIC_A)
                assert actual == expected_count, f"runtime {table}: expected {expected_count}, got {actual}"
            cursor.execute("SELECT count(*) FROM patients WHERE clinic_id = %s", (CLINIC_B,))
            assert cursor.fetchone()[0] == 0, "clinic A runtime context must not see clinic B patients"

    print("Seed verification passed: admin counts match and runtime clinic A cannot see clinic B.")


if __name__ == "__main__":
    main()

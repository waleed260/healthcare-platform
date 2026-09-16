import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.core.security import hash_token
from app.db.tenant import set_tenant_context
from app.modules.appointments.routes import _managed_appointment
from app.modules.operations.jobs import claim_next_job
from app.modules.websites.routes import _public_clinic_id


pytestmark = pytest.mark.integration


def _database_urls() -> tuple[str, str]:
    admin_url = os.getenv("TEST_ADMIN_DATABASE_URL")
    runtime_url = os.getenv("TEST_DATABASE_URL")
    if not admin_url or not runtime_url:
        pytest.skip("PostgreSQL integration URLs are not configured")
    return admin_url, runtime_url


def test_two_tenants_cannot_read_or_write_each_other() -> None:
    admin_url, runtime_url = _database_urls()
    admin = create_engine(admin_url)
    runtime = create_engine(runtime_url)
    clinic_a, clinic_b = uuid4(), uuid4()

    with admin.begin() as connection:
        connection.execute(
            text("INSERT INTO clinics (id, name, slug) VALUES (:id, :name, :slug)"),
            [
                {"id": clinic_a, "name": "Synthetic A", "slug": f"synthetic-a-{clinic_a}"},
                {"id": clinic_b, "name": "Synthetic B", "slug": f"synthetic-b-{clinic_b}"},
            ],
        )
        connection.execute(
            text("INSERT INTO tenant_probe_records (clinic_id, label) VALUES (:clinic_id, :label)"),
            [{"clinic_id": clinic_a, "label": "A-only"}, {"clinic_id": clinic_b, "label": "B-only"}],
        )

    try:
        with runtime.begin() as connection:
            set_tenant_context(connection, clinic_a)
            rows = connection.execute(text("SELECT label FROM tenant_probe_records ORDER BY label")).scalars().all()
            assert rows == ["A-only"]
            with pytest.raises(Exception):
                connection.execute(
                    text("INSERT INTO tenant_probe_records (clinic_id, label) VALUES (:clinic_id, 'forbidden')"),
                    {"clinic_id": clinic_b},
                )
    finally:
        with admin.begin() as connection:
            connection.execute(text("DELETE FROM tenant_probe_records WHERE clinic_id IN (:a, :b)"), {"a": clinic_a, "b": clinic_b})
            connection.execute(text("DELETE FROM clinics WHERE id IN (:a, :b)"), {"a": clinic_a, "b": clinic_b})


def test_booking_management_tokens_cannot_cross_tenant_contexts() -> None:
    admin_url, runtime_url = _database_urls()
    admin = create_engine(admin_url)
    runtime = create_engine(runtime_url)
    clinic_a, clinic_b = uuid4(), uuid4()
    branch_a, branch_b = uuid4(), uuid4()
    service_a, service_b = uuid4(), uuid4()
    patient_a, patient_b = uuid4(), uuid4()
    appointment_a, appointment_b = uuid4(), uuid4()
    token_a, token_b = "synthetic-management-token-a", "synthetic-management-token-b"
    try:
        with admin.begin() as connection:
            connection.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:a, 'Token clinic A', :slug_a), (:b, 'Token clinic B', :slug_b)"), {"a": clinic_a, "b": clinic_b, "slug_a": f"token-a-{clinic_a}", "slug_b": f"token-b-{clinic_b}"})
            connection.execute(text("INSERT INTO branches (id, clinic_id, code, name) VALUES (:branch_a, :clinic_a, 'A', 'Branch A'), (:branch_b, :clinic_b, 'B', 'Branch B')"), {"branch_a": branch_a, "clinic_a": clinic_a, "branch_b": branch_b, "clinic_b": clinic_b})
            connection.execute(text("INSERT INTO services (id, clinic_id, name, duration_minutes) VALUES (:service_a, :clinic_a, 'Synthetic service A', 30), (:service_b, :clinic_b, 'Synthetic service B', 30)"), {"service_a": service_a, "clinic_a": clinic_a, "service_b": service_b, "clinic_b": clinic_b})
            connection.execute(text("INSERT INTO patients (id, clinic_id, patient_number, full_name) VALUES (:patient_a, :clinic_a, 'TOKEN-A', 'Synthetic Patient A'), (:patient_b, :clinic_b, 'TOKEN-B', 'Synthetic Patient B')"), {"patient_a": patient_a, "clinic_a": clinic_a, "patient_b": patient_b, "clinic_b": clinic_b})
            connection.execute(text("""
                INSERT INTO appointments (id, clinic_id, branch_id, service_id, patient_id, starts_at, ends_at, occupancy_start, occupancy_end, reference, idempotency_key, idempotency_body_hash)
                VALUES
                  (:appointment_a, :clinic_a, :branch_a, :service_a, :patient_a, '2030-01-01 09:00+00', '2030-01-01 09:30+00', '2030-01-01 09:00+00', '2030-01-01 09:30+00', 'TOKEN-APT-A', 'token-key-a', repeat('a', 64)),
                  (:appointment_b, :clinic_b, :branch_b, :service_b, :patient_b, '2030-01-01 09:00+00', '2030-01-01 09:30+00', '2030-01-01 09:00+00', '2030-01-01 09:30+00', 'TOKEN-APT-B', 'token-key-b', repeat('b', 64))
            """), {"appointment_a": appointment_a, "clinic_a": clinic_a, "branch_a": branch_a, "service_a": service_a, "patient_a": patient_a, "appointment_b": appointment_b, "clinic_b": clinic_b, "branch_b": branch_b, "service_b": service_b, "patient_b": patient_b})
            connection.execute(text("INSERT INTO booking_management_tokens (clinic_id, appointment_id, secret_hash, expires_at) VALUES (:clinic_a, :appointment_a, :hash_a, '2031-01-01 00:00+00'), (:clinic_b, :appointment_b, :hash_b, '2031-01-01 00:00+00')"), {"clinic_a": clinic_a, "appointment_a": appointment_a, "hash_a": hash_token(token_a), "clinic_b": clinic_b, "appointment_b": appointment_b, "hash_b": hash_token(token_b)})
        with runtime.begin() as connection:
            set_tenant_context(connection, clinic_a)
            own = _managed_appointment(connection, clinic_a, "TOKEN-APT-A", token_a)
            assert own["id"] == appointment_a
            with pytest.raises(HTTPException) as error:
                _managed_appointment(connection, clinic_a, "TOKEN-APT-A", token_b)
            assert error.value.status_code == 404
            set_tenant_context(connection, clinic_b)
            with pytest.raises(HTTPException) as error:
                _managed_appointment(connection, clinic_b, "TOKEN-APT-B", token_a)
            assert error.value.status_code == 404
    finally:
        with admin.begin() as connection:
            connection.execute(text("DELETE FROM booking_management_tokens WHERE clinic_id IN (:a, :b)"), {"a": clinic_a, "b": clinic_b})
            connection.execute(text("DELETE FROM appointments WHERE clinic_id IN (:a, :b)"), {"a": clinic_a, "b": clinic_b})
            connection.execute(text("DELETE FROM patients WHERE clinic_id IN (:a, :b)"), {"a": clinic_a, "b": clinic_b})
            connection.execute(text("DELETE FROM services WHERE clinic_id IN (:a, :b)"), {"a": clinic_a, "b": clinic_b})
            connection.execute(text("DELETE FROM branches WHERE clinic_id IN (:a, :b)"), {"a": clinic_a, "b": clinic_b})
            connection.execute(text("DELETE FROM clinics WHERE id IN (:a, :b)"), {"a": clinic_a, "b": clinic_b})


def test_verified_public_host_requires_active_non_archived_clinic() -> None:
    admin_url, runtime_url = _database_urls()
    admin = create_engine(admin_url)
    runtime = create_engine(runtime_url)
    active_clinic, suspended_clinic, archived_clinic = uuid4(), uuid4(), uuid4()
    hosts = {
        active_clinic: f"active-{active_clinic}.example.test",
        suspended_clinic: f"suspended-{suspended_clinic}.example.test",
        archived_clinic: f"archived-{archived_clinic}.example.test",
    }
    try:
        with admin.begin() as connection:
            connection.execute(text("""
                INSERT INTO clinics (id, name, slug, status, archived_at)
                VALUES
                  (:active, 'Active synthetic clinic', :active_slug, 'active', NULL),
                  (:suspended, 'Suspended synthetic clinic', :suspended_slug, 'suspended', NULL),
                  (:archived, 'Archived synthetic clinic', :archived_slug, 'active', now())
            """), {"active": active_clinic, "suspended": suspended_clinic, "archived": archived_clinic, "active_slug": f"active-host-{active_clinic}", "suspended_slug": f"suspended-host-{suspended_clinic}", "archived_slug": f"archived-host-{archived_clinic}"})
            connection.execute(text("""
                INSERT INTO domain_verifications (clinic_id, hostname, expected_dns_proof, observed_status)
                VALUES (:active, :active_host, 'proof-a', 'verified'),
                       (:suspended, :suspended_host, 'proof-b', 'verified'),
                       (:archived, :archived_host, 'proof-c', 'verified')
            """), {"active": active_clinic, "suspended": suspended_clinic, "archived": archived_clinic, "active_host": hosts[active_clinic], "suspended_host": hosts[suspended_clinic], "archived_host": hosts[archived_clinic]})
        with runtime.begin() as connection:
            assert _public_clinic_id(connection, hosts[active_clinic]) == active_clinic
            assert _public_clinic_id(connection, hosts[suspended_clinic]) is None
            assert _public_clinic_id(connection, hosts[archived_clinic]) is None
    finally:
        with admin.begin() as connection:
            connection.execute(text("DELETE FROM domain_verifications WHERE clinic_id IN (:active, :suspended, :archived)"), {"active": active_clinic, "suspended": suspended_clinic, "archived": archived_clinic})
            connection.execute(text("DELETE FROM clinics WHERE id IN (:active, :suspended, :archived)"), {"active": active_clinic, "suspended": suspended_clinic, "archived": archived_clinic})


def test_background_job_claim_is_tenant_scoped() -> None:
    admin_url, runtime_url = _database_urls()
    admin = create_engine(admin_url)
    runtime = create_engine(runtime_url)
    clinic_a, clinic_b = uuid4(), uuid4()
    try:
        with admin.begin() as connection:
            connection.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:a, 'Job synthetic A', :slug_a), (:b, 'Job synthetic B', :slug_b)"), {"a": clinic_a, "b": clinic_b, "slug_a": f"job-a-{clinic_a}", "slug_b": f"job-b-{clinic_b}"})
            connection.execute(text("INSERT INTO background_jobs (clinic_id, job_key, job_type) VALUES (:a, 'job-a', 'document_scan'), (:b, 'job-b', 'document_scan')"), {"a": clinic_a, "b": clinic_b})
        with runtime.begin() as connection:
            claimed = claim_next_job(connection, clinic_a, job_type="document_scan")
            assert claimed is not None
            assert claimed["clinic_id"] == clinic_a
            assert claimed["job_key"] == "job-a"
            assert claim_next_job(connection, clinic_a, job_type="document_scan") is None
    finally:
        with admin.begin() as connection:
            connection.execute(text("DELETE FROM background_jobs WHERE clinic_id IN (:a, :b)"), {"a": clinic_a, "b": clinic_b})
            connection.execute(text("DELETE FROM clinics WHERE id IN (:a, :b)"), {"a": clinic_a, "b": clinic_b})

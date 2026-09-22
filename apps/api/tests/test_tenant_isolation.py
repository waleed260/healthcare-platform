import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.core.security import hash_token
from app.db.tenant import set_tenant_context
from app.modules.appointments.routes import _managed_appointment
from app.modules.files.routes import _require_document
from app.modules.operations.jobs import claim_next_job
from app.modules.websites.routes import _public_clinic_id


pytestmark = pytest.mark.integration


def _database_urls() -> tuple[str, str]:
    admin_url = os.getenv("TEST_ADMIN_DATABASE_URL")
    runtime_url = os.getenv("TEST_DATABASE_URL")
    if not admin_url or not runtime_url:
        pytest.skip("PostgreSQL integration URLs are not configured")
    return admin_url, runtime_url


def test_required_clinic_tables_have_forced_rls() -> None:
    """Keep the specification's mandatory RLS contract executable in CI."""
    _, runtime_url = _database_urls()
    runtime = create_engine(runtime_url)
    required = {
        "branches", "user_roles", "user_branch_scopes", "branch_hours",
        "clinic_holidays", "doctor_profiles", "services", "doctor_services",
        "branch_doctors", "branch_services", "rooms", "resources", "patients",
        "appointments", "appointment_history", "booking_management_tokens",
        "appointment_reschedule_requests", "queue_entries",
        "follow_up_tasks", "notifications", "browser_push_subscriptions",
        "patient_documents", "file_scan_events", "patient_contacts", "tags",
        "patient_tags", "patient_notes", "consent_records", "patient_merge_events",
        "privacy_requests", "export_jobs", "background_jobs", "clinic_subscriptions",
        "support_access_sessions", "audit_events", "clinic_feature_usage",
        "availability_rules", "leave_blocks", "blocked_slots", "resource_blocks",
        "booking_questions", "service_booking_questions", "appointment_answers",
        "websites", "website_versions", "website_pages", "website_sections",
        "website_media", "domain_verifications", "website_media_scan_events",
        "website_preview_tokens", "document_access_events", "doctor_rooms",
        "access_tokens", "clinic_care_policies",
        "patient_care_team",
        "tenant_probe_records", "staff_invitations",
    }
    with runtime.connect() as connection:
        rows = connection.execute(text("""
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                   EXISTS (SELECT 1 FROM pg_policies p WHERE p.schemaname = 'public' AND p.tablename = c.relname) AS has_policy
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = ANY(:tables)
        """), {"tables": list(required)}).mappings().all()
        assert connection.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_access_tokens_user_tenant'
                  AND contype = 'f'
            )
        """)).scalar_one()
    found = {row["relname"] for row in rows}
    assert found == required
    assert all(row["relrowsecurity"] and row["relforcerowsecurity"] and row["has_policy"] for row in rows)


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


def test_private_documents_are_isolated_and_cross_tenant_object_access_is_not_found() -> None:
    admin_url, runtime_url = _database_urls()
    admin = create_engine(admin_url)
    runtime = create_engine(runtime_url)
    clinic_a, clinic_b = uuid4(), uuid4()
    user_a, user_b = uuid4(), uuid4()
    patient_a, patient_b = uuid4(), uuid4()
    document_a, document_b = uuid4(), uuid4()
    try:
        with admin.begin() as connection:
            connection.execute(text("""
                INSERT INTO clinics (id, name, slug) VALUES
                  (:clinic_a, 'Documents synthetic A', :slug_a),
                  (:clinic_b, 'Documents synthetic B', :slug_b)
            """), {"clinic_a": clinic_a, "clinic_b": clinic_b, "slug_a": f"documents-a-{clinic_a}", "slug_b": f"documents-b-{clinic_b}"})
            connection.execute(text("""
                INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash) VALUES
                  (:user_a, :clinic_a, :email_a, 'Synthetic Uploader A', 'synthetic-password-hash'),
                  (:user_b, :clinic_b, :email_b, 'Synthetic Uploader B', 'synthetic-password-hash')
            """), {"user_a": user_a, "clinic_a": clinic_a, "email_a": f"uploader-a-{user_a}@example.test", "user_b": user_b, "clinic_b": clinic_b, "email_b": f"uploader-b-{user_b}@example.test"})
            connection.execute(text("""
                INSERT INTO patients (id, clinic_id, patient_number, full_name) VALUES
                  (:patient_a, :clinic_a, 'DOC-A', 'Synthetic Document Patient A'),
                  (:patient_b, :clinic_b, 'DOC-B', 'Synthetic Document Patient B')
            """), {"patient_a": patient_a, "clinic_a": clinic_a, "patient_b": patient_b, "clinic_b": clinic_b})
            connection.execute(text("""
                INSERT INTO patient_documents
                  (id, clinic_id, patient_id, uploaded_by_user_id, storage_key, original_filename, mime_type, size_bytes, content_sha256, scan_status)
                VALUES
                  (:document_a, :clinic_a, :patient_a, :user_a, :key_a, 'document.pdf', 'application/pdf', 10, repeat('a', 64), 'clean'),
                  (:document_b, :clinic_b, :patient_b, :user_b, :key_b, 'document.pdf', 'application/pdf', 10, repeat('b', 64), 'clean')
            """), {"document_a": document_a, "clinic_a": clinic_a, "patient_a": patient_a, "user_a": user_a, "key_a": f"{clinic_a}/{patient_a}/{document_a}.pdf", "document_b": document_b, "clinic_b": clinic_b, "patient_b": patient_b, "user_b": user_b, "key_b": f"{clinic_b}/{patient_b}/{document_b}.pdf"})

        with runtime.begin() as connection:
            set_tenant_context(connection, clinic_a, user_a)
            visible = connection.execute(text("SELECT id FROM patient_documents ORDER BY id")).scalars().all()
            assert visible == [document_a]
            with pytest.raises(Exception):
                with connection.begin_nested():
                    connection.execute(text("""
                        INSERT INTO patient_documents
                          (id, clinic_id, patient_id, uploaded_by_user_id, storage_key, original_filename, mime_type, size_bytes, content_sha256, scan_status)
                        VALUES (:id, :clinic_id, :patient_id, :user_id, :storage_key, 'forbidden.pdf', 'application/pdf', 10, repeat('c', 64), 'clean')
                    """), {"id": uuid4(), "clinic_id": clinic_b, "patient_id": patient_b, "user_id": user_b, "storage_key": f"{clinic_b}/forbidden.pdf"})
            with pytest.raises(HTTPException) as error:
                _require_document(connection, {"clinic_id": clinic_a, "user_id": user_a}, document_b)
            assert error.value.status_code == 404
            set_tenant_context(connection, clinic_b, user_b)
            assert connection.execute(text("SELECT id FROM patient_documents")).scalars().all() == [document_b]
    finally:
        with admin.begin() as connection:
            connection.execute(text("DELETE FROM patient_documents WHERE clinic_id IN (:a, :b)"), {"a": clinic_a, "b": clinic_b})
            connection.execute(text("DELETE FROM patients WHERE clinic_id IN (:a, :b)"), {"a": clinic_a, "b": clinic_b})
            connection.execute(text("DELETE FROM users WHERE id IN (:a, :b)"), {"a": user_a, "b": user_b})
            connection.execute(text("DELETE FROM clinics WHERE id IN (:a, :b)"), {"a": clinic_a, "b": clinic_b})


def test_privacy_requests_and_exports_are_isolated_and_foreign_targets_fail() -> None:
    """Exercise the privacy/export portion of the two-clinic RLS matrix."""
    admin_url, runtime_url = _database_urls()
    admin = create_engine(admin_url)
    runtime = create_engine(runtime_url)
    clinic_a, clinic_b = uuid4(), uuid4()
    user_a, user_b = uuid4(), uuid4()
    patient_a, patient_b = uuid4(), uuid4()
    request_a, request_b = uuid4(), uuid4()
    export_a, export_b = uuid4(), uuid4()
    try:
        with admin.begin() as connection:
            connection.execute(text("""
                INSERT INTO clinics (id, name, slug) VALUES
                  (:clinic_a, 'Privacy synthetic A', :slug_a),
                  (:clinic_b, 'Privacy synthetic B', :slug_b)
            """), {"clinic_a": clinic_a, "clinic_b": clinic_b, "slug_a": f"privacy-a-{clinic_a}", "slug_b": f"privacy-b-{clinic_b}"})
            connection.execute(text("""
                INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash) VALUES
                  (:user_a, :clinic_a, :email_a, 'Synthetic Privacy A', 'synthetic-password-hash'),
                  (:user_b, :clinic_b, :email_b, 'Synthetic Privacy B', 'synthetic-password-hash')
            """), {"user_a": user_a, "clinic_a": clinic_a, "email_a": f"privacy-a-{user_a}@example.test", "user_b": user_b, "clinic_b": clinic_b, "email_b": f"privacy-b-{user_b}@example.test"})
            connection.execute(text("""
                INSERT INTO patients (id, clinic_id, patient_number, full_name) VALUES
                  (:patient_a, :clinic_a, 'PRIV-A', 'Synthetic Privacy Patient A'),
                  (:patient_b, :clinic_b, 'PRIV-B', 'Synthetic Privacy Patient B')
            """), {"patient_a": patient_a, "clinic_a": clinic_a, "patient_b": patient_b, "clinic_b": clinic_b})
            connection.execute(text("""
                INSERT INTO privacy_requests (id, clinic_id, patient_id, request_type, reason, requested_by_user_id)
                VALUES (:request_a, :clinic_a, :patient_a, 'access', 'Synthetic access request A', :user_a),
                       (:request_b, :clinic_b, :patient_b, 'deletion', 'Synthetic deletion request B', :user_b)
            """), {"request_a": request_a, "clinic_a": clinic_a, "patient_a": patient_a, "user_a": user_a, "request_b": request_b, "clinic_b": clinic_b, "patient_b": patient_b, "user_b": user_b})
            connection.execute(text("""
                INSERT INTO export_jobs (id, clinic_id, requested_by_user_id, patient_id, privacy_request_id, export_type)
                VALUES (:export_a, :clinic_a, :user_a, :patient_a, :request_a, 'patient_access'),
                       (:export_b, :clinic_b, :user_b, :patient_b, :request_b, 'patient_access')
            """), {"export_a": export_a, "clinic_a": clinic_a, "user_a": user_a, "patient_a": patient_a, "request_a": request_a, "export_b": export_b, "clinic_b": clinic_b, "user_b": user_b, "patient_b": patient_b, "request_b": request_b})
        with runtime.begin() as connection:
            set_tenant_context(connection, clinic_a, user_a)
            assert connection.execute(text("SELECT id FROM privacy_requests ORDER BY id")).scalars().all() == [request_a]
            assert connection.execute(text("SELECT id FROM export_jobs ORDER BY id")).scalars().all() == [export_a]
            with pytest.raises(Exception):
                with connection.begin_nested():
                    connection.execute(text("""
                        INSERT INTO export_jobs (clinic_id, requested_by_user_id, patient_id, privacy_request_id, export_type)
                        VALUES (:clinic_b, :user_b, :patient_b, :request_b, 'patient_access')
                    """), {"clinic_b": clinic_b, "user_b": user_b, "patient_b": patient_b, "request_b": request_b})
            set_tenant_context(connection, clinic_b, user_b)
            assert connection.execute(text("SELECT id FROM privacy_requests ORDER BY id")).scalars().all() == [request_b]
            assert connection.execute(text("SELECT id FROM export_jobs ORDER BY id")).scalars().all() == [export_b]
    finally:
        with admin.begin() as connection:
            connection.execute(text("DELETE FROM export_jobs WHERE clinic_id IN (:a, :b)"), {"a": clinic_a, "b": clinic_b})
            connection.execute(text("DELETE FROM privacy_requests WHERE clinic_id IN (:a, :b)"), {"a": clinic_a, "b": clinic_b})
            connection.execute(text("DELETE FROM patients WHERE clinic_id IN (:a, :b)"), {"a": clinic_a, "b": clinic_b})
            connection.execute(text("DELETE FROM users WHERE id IN (:a, :b)"), {"a": user_a, "b": user_b})
            connection.execute(text("DELETE FROM clinics WHERE id IN (:a, :b)"), {"a": clinic_a, "b": clinic_b})


def test_catalog_rows_are_isolated_before_cross_tenant_assignments() -> None:
    admin_url, runtime_url = _database_urls()
    admin = create_engine(admin_url)
    runtime = create_engine(runtime_url)
    clinic_a, clinic_b = uuid4(), uuid4()
    branch_a, branch_b = uuid4(), uuid4()
    service_a, service_b = uuid4(), uuid4()
    try:
        with admin.begin() as connection:
            connection.execute(text("""
                INSERT INTO clinics (id, name, slug) VALUES
                  (:clinic_a, 'Catalog synthetic A', :slug_a),
                  (:clinic_b, 'Catalog synthetic B', :slug_b)
            """), {"clinic_a": clinic_a, "clinic_b": clinic_b, "slug_a": f"catalog-a-{clinic_a}", "slug_b": f"catalog-b-{clinic_b}"})
            connection.execute(text("""
                INSERT INTO branches (id, clinic_id, code, name) VALUES
                  (:branch_a, :clinic_a, 'A', 'Branch A'),
                  (:branch_b, :clinic_b, 'B', 'Branch B')
            """), {"branch_a": branch_a, "clinic_a": clinic_a, "branch_b": branch_b, "clinic_b": clinic_b})
            connection.execute(text("""
                INSERT INTO services (id, clinic_id, name, duration_minutes) VALUES
                  (:service_a, :clinic_a, 'Service A', 30),
                  (:service_b, :clinic_b, 'Service B', 30)
            """), {"service_a": service_a, "clinic_a": clinic_a, "service_b": service_b, "clinic_b": clinic_b})
        with runtime.begin() as connection:
            set_tenant_context(connection, clinic_a)
            assert connection.execute(text("SELECT id FROM branches")).scalars().all() == [branch_a]
            assert connection.execute(text("SELECT id FROM services")).scalars().all() == [service_a]
            with pytest.raises(Exception):
                with connection.begin_nested():
                    connection.execute(text("INSERT INTO branches (id, clinic_id, code, name) VALUES (:id, :clinic_id, 'FORBIDDEN', 'Forbidden')"), {"id": uuid4(), "clinic_id": clinic_b})
    finally:
        with admin.begin() as connection:
            connection.execute(text("DELETE FROM services WHERE clinic_id IN (:a, :b)"), {"a": clinic_a, "b": clinic_b})
            connection.execute(text("DELETE FROM branches WHERE clinic_id IN (:a, :b)"), {"a": clinic_a, "b": clinic_b})
            connection.execute(text("DELETE FROM clinics WHERE id IN (:a, :b)"), {"a": clinic_a, "b": clinic_b})

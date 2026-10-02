"""PostgreSQL evidence that patient merge moves every patient-owned relationship.

Regression for the merge that repointed only a handful of tables and silently
orphaned documents, media, treatment plans, packages, prescriptions, clinical
forms/tools and invoices on the archived source patient. Two tests:

* ``test_merge_registry_covers_every_patient_scoped_table`` is a structural
  guard — it asks the database for every table with a ``patient_id`` column and
  fails if one is not handled by the merge service. A future migration that adds
  a patient-owned table will fail here until it is registered.
* ``test_merge_moves_all_relationships_and_tombstones_source`` exercises the
  real moves, the clinical-tool-state conflict rule, indirect children that
  follow their parent, the converted-lead pointer and the source tombstone.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from app.db.tenant import set_tenant_context
from app.modules.crm.merge import _DEDUPE_MEMBERSHIP, _DIRECT_REPOINT, merge_patients

pytestmark = pytest.mark.integration

# Every table carrying a direct patient_id is handled by one of these paths.
_COVERED = set(_DIRECT_REPOINT) | {table for table, _, _ in _DEDUPE_MEMBERSHIP} | {"clinical_tool_states"}


def _database_urls() -> tuple[str, str]:
    admin_url = os.getenv("TEST_ADMIN_DATABASE_URL")
    runtime_url = os.getenv("TEST_DATABASE_URL")
    if not admin_url or not runtime_url:
        pytest.skip("PostgreSQL integration URLs are not configured")
    return admin_url, runtime_url


def test_merge_registry_covers_every_patient_scoped_table() -> None:
    admin_url, _ = _database_urls()
    admin = create_engine(admin_url)
    with admin.connect() as connection:
        tables = set(connection.execute(text("""
            SELECT table_name FROM information_schema.columns
            WHERE table_schema = 'public' AND column_name = 'patient_id'
        """)).scalars().all())
    missing = tables - _COVERED
    assert not missing, f"patient-scoped tables not handled by merge_patients: {sorted(missing)}"


def test_merge_moves_all_relationships_and_tombstones_source() -> None:
    admin_url, runtime_url = _database_urls()
    admin = create_engine(admin_url)
    runtime = create_engine(runtime_url)
    clinic = uuid4()
    user = uuid4()
    source, target = uuid4(), uuid4()
    template = uuid4()
    package_def = uuid4()
    source_package = uuid4()
    invoice = uuid4()
    lead = uuid4()
    try:
        with admin.begin() as c:
            c.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:id, 'Merge Synthetic', :slug)"), {"id": clinic, "slug": f"merge-{clinic}"})
            c.execute(text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, status) VALUES (:id, :clinic, :email, 'Merge User', 'x', 'active')"), {"id": user, "clinic": clinic, "email": f"merge-{user}@example.test"})
            c.execute(text("""
                INSERT INTO patients (id, clinic_id, patient_number, full_name) VALUES
                  (:source, :clinic, 'MERGE-SRC', 'Merge Source'),
                  (:target, :clinic, 'MERGE-TGT', 'Merge Target')
            """), {"source": source, "target": target, "clinic": clinic})
            # Direct patient_id rows on the SOURCE.
            c.execute(text("INSERT INTO patient_documents (clinic_id, patient_id, uploaded_by_user_id, storage_key, original_filename, mime_type, size_bytes, content_sha256) VALUES (:clinic, :p, :u, :key, 'f.pdf', 'application/pdf', 1, 'h')"), {"clinic": clinic, "p": source, "u": user, "key": f"doc-{uuid4()}"})
            c.execute(text("INSERT INTO treatment_plans (clinic_id, patient_id, created_by_user_id, title) VALUES (:clinic, :p, :u, 'Plan')"), {"clinic": clinic, "p": source, "u": user})
            c.execute(text("INSERT INTO prescriptions (clinic_id, patient_id, prescribed_by_user_id, medication_name) VALUES (:clinic, :p, :u, 'Med')"), {"clinic": clinic, "p": source, "u": user})
            c.execute(text("INSERT INTO clinical_form_templates (id, clinic_id, form_key, name, created_by_user_id) VALUES (:id, :clinic, 'k', 'T', :u)"), {"id": template, "clinic": clinic, "u": user})
            c.execute(text("INSERT INTO clinical_form_responses (clinic_id, patient_id, template_id) VALUES (:clinic, :p, :tpl)"), {"clinic": clinic, "p": source, "tpl": template})
            c.execute(text("INSERT INTO invoices (id, clinic_id, patient_id, invoice_number, currency, created_by_user_id) VALUES (:id, :clinic, :p, 'INV-1', 'USD', :u)"), {"id": invoice, "clinic": clinic, "p": source, "u": user})
            c.execute(text("INSERT INTO invoice_lines (clinic_id, invoice_id, description, unit_price_minor, line_total_minor) VALUES (:clinic, :inv, 'line', 100, 100)"), {"clinic": clinic, "inv": invoice})
            c.execute(text("INSERT INTO package_definitions (id, clinic_id, name, total_price_minor, currency, validity_days) VALUES (:id, :clinic, 'Pkg', 100, 'USD', 30)"), {"id": package_def, "clinic": clinic})
            c.execute(text("INSERT INTO patient_packages (id, clinic_id, patient_id, package_definition_id, expires_at, total_sessions) VALUES (:id, :clinic, :p, :def, now() + interval '30 days', 5)"), {"id": source_package, "clinic": clinic, "p": source, "def": package_def})
            c.execute(text("INSERT INTO package_sessions (clinic_id, patient_package_id) VALUES (:clinic, :pkg)"), {"clinic": clinic, "pkg": source_package})
            # clinical_tool_states conflict: both have 'dental_chart'; only source has 'norwood'.
            c.execute(text("INSERT INTO clinical_tool_states (clinic_id, patient_id, tool_key) VALUES (:clinic, :p, 'dental_chart'), (:clinic, :p, 'norwood')"), {"clinic": clinic, "p": source})
            c.execute(text("INSERT INTO clinical_tool_states (clinic_id, patient_id, tool_key) VALUES (:clinic, :p, 'dental_chart')"), {"clinic": clinic, "p": target})
            # A converted lead pointing at the source patient.
            c.execute(text("INSERT INTO leads (id, clinic_id, full_name, source, converted_to_patient_id) VALUES (:id, :clinic, 'Lead', 'web', :p)"), {"id": lead, "clinic": clinic, "p": source})

        with runtime.begin() as c:
            set_tenant_context(c, clinic, user)
            # merge_patients runs raw SQL on this connection; wrap it in a Session-like
            # adapter is unnecessary because it only uses .execute().
            counts = merge_patients(c, clinic_id=clinic, actor_user_id=user, source_id=source, target_id=target, reason="duplicate")

        with runtime.begin() as c:
            set_tenant_context(c, clinic, user)
            moved = {
                "patient_documents": "SELECT count(*) FROM patient_documents WHERE patient_id = :t",
                "treatment_plans": "SELECT count(*) FROM treatment_plans WHERE patient_id = :t",
                "prescriptions": "SELECT count(*) FROM prescriptions WHERE patient_id = :t",
                "clinical_form_responses": "SELECT count(*) FROM clinical_form_responses WHERE patient_id = :t",
                "invoices": "SELECT count(*) FROM invoices WHERE patient_id = :t",
                "patient_packages": "SELECT count(*) FROM patient_packages WHERE patient_id = :t",
            }
            for table, query in moved.items():
                assert c.execute(text(query), {"t": target}).scalar_one() == 1, f"{table} did not move to target"
                leftover = c.execute(text(f"SELECT count(*) FROM {table} WHERE patient_id = :s"), {"s": source}).scalar_one()
                assert leftover == 0, f"{table} still has rows on the source"

            # Indirect children follow their parent (invoice_line via invoice, package_session via package).
            assert c.execute(text("SELECT count(*) FROM invoice_lines l JOIN invoices i ON i.clinic_id = l.clinic_id AND i.id = l.invoice_id WHERE i.patient_id = :t"), {"t": target}).scalar_one() == 1
            assert c.execute(text("SELECT count(*) FROM package_sessions s JOIN patient_packages p ON p.clinic_id = s.clinic_id AND p.id = s.patient_package_id WHERE p.patient_id = :t"), {"t": target}).scalar_one() == 1

            # Conflict rule: target keeps its own dental_chart, source's duplicate is dropped, norwood moves.
            tool_keys = sorted(c.execute(text("SELECT tool_key FROM clinical_tool_states WHERE patient_id = :t ORDER BY tool_key"), {"t": target}).scalars().all())
            assert tool_keys == ["dental_chart", "norwood"], tool_keys
            assert c.execute(text("SELECT count(*) FROM clinical_tool_states WHERE patient_id = :s"), {"s": source}).scalar_one() == 0

            # Converted lead now points at the surviving patient.
            assert c.execute(text("SELECT converted_to_patient_id FROM leads WHERE id = :id"), {"id": lead}).scalar_one() == target

            # Source is tombstoned, not deleted, and the merge is audited.
            row = c.execute(text("SELECT status, duplicate_of FROM patients WHERE id = :s"), {"s": source}).mappings().one()
            assert row["status"] == "merged" and row["duplicate_of"] == target
            assert c.execute(text("SELECT count(*) FROM patient_merge_events WHERE source_patient_id = :s AND target_patient_id = :t"), {"s": source, "t": target}).scalar_one() == 1

        assert counts["invoices"] == 1 and counts["leads.converted_to_patient_id"] == 1 and counts["clinical_tool_states"] == 1
    finally:
        with admin.begin() as c:
            for table in ("package_sessions", "patient_packages", "package_definitions", "invoice_lines", "invoices", "clinical_tool_states", "clinical_form_responses", "clinical_form_templates", "prescriptions", "treatment_plans", "patient_documents", "patient_merge_events"):
                c.execute(text(f"DELETE FROM {table} WHERE clinic_id = :clinic"), {"clinic": clinic})
            c.execute(text("UPDATE leads SET converted_to_patient_id = NULL WHERE clinic_id = :clinic"), {"clinic": clinic})
            c.execute(text("DELETE FROM leads WHERE clinic_id = :clinic"), {"clinic": clinic})
            c.execute(text("DELETE FROM patients WHERE clinic_id = :clinic"), {"clinic": clinic})
            c.execute(text("DELETE FROM users WHERE clinic_id = :clinic"), {"clinic": clinic})
            c.execute(text("DELETE FROM clinics WHERE id = :clinic"), {"clinic": clinic})

"""PostgreSQL evidence for the read-only merge reconciliation job.

Simulates a merge performed on the OLD buggy code (an invoice left pointing at
the source, source not tombstoned) and asserts the scan reports it, while a
clean merge produces no finding.
"""
from __future__ import annotations

import os
from uuid import uuid4

import psycopg
import pytest

from scripts.reconcile_merges import reconcile

pytestmark = pytest.mark.integration


def _admin_url() -> str:
    url = os.getenv("TEST_ADMIN_DATABASE_URL")
    if not url:
        pytest.skip("PostgreSQL integration URLs are not configured")
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def test_reconcile_reports_orphans_and_ignores_clean_merges() -> None:
    conn = psycopg.connect(_admin_url())
    clinic = uuid4()
    user = uuid4()
    dirty_src, dirty_tgt = uuid4(), uuid4()
    clean_src, clean_tgt = uuid4(), uuid4()
    invoice = uuid4()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO clinics (id, name, slug) VALUES (%s, 'Reconcile Synthetic', %s)", (clinic, f"reconcile-{clinic}"))
            cur.execute("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, status) VALUES (%s, %s, %s, 'Reconcile User', 'x', 'active')", (user, clinic, f"reconcile-{user}@example.test"))
            cur.execute("""
                INSERT INTO patients (id, clinic_id, patient_number, full_name, status, duplicate_of) VALUES
                  (%s, %s, 'REC-DSRC', 'Dirty Source', 'active', NULL),
                  (%s, %s, 'REC-DTGT', 'Dirty Target', 'active', NULL),
                  (%s, %s, 'REC-CSRC', 'Clean Source', 'merged', %s),
                  (%s, %s, 'REC-CTGT', 'Clean Target', 'active', NULL)
            """, (dirty_src, clinic, dirty_tgt, clinic, clean_src, clinic, clean_tgt, clean_tgt, clinic))
            # Both merges are recorded in the authoritative log.
            cur.execute("INSERT INTO patient_merge_events (clinic_id, source_patient_id, target_patient_id, actor_user_id, reason) VALUES (%s, %s, %s, %s, 'old-merge'), (%s, %s, %s, %s, 'good-merge')",
                        (clinic, dirty_src, dirty_tgt, user, clinic, clean_src, clean_tgt, user))
            # Dirty merge: an invoice still points at the source, and the source was never tombstoned.
            cur.execute("INSERT INTO invoices (id, clinic_id, patient_id, invoice_number, currency, created_by_user_id) VALUES (%s, %s, %s, 'REC-INV-1', 'USD', %s)", (invoice, clinic, dirty_src, user))
            conn.commit()

        findings = reconcile(conn)
        by_source = {f.source_patient_id: f for f in findings}

        assert str(dirty_src) in by_source, "the orphaned merge was not reported"
        dirty = by_source[str(dirty_src)]
        assert dirty.not_tombstoned is True
        assert dirty.orphans.get("invoices.patient_id") == 1
        assert str(clean_src) not in by_source, "a clean merge should not be reported"
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM invoices WHERE clinic_id = %s", (clinic,))
            cur.execute("DELETE FROM patient_merge_events WHERE clinic_id = %s", (clinic,))
            cur.execute("DELETE FROM patients WHERE clinic_id = %s", (clinic,))
            cur.execute("DELETE FROM users WHERE clinic_id = %s", (clinic,))
            cur.execute("DELETE FROM clinics WHERE id = %s", (clinic,))
            conn.commit()
        conn.close()

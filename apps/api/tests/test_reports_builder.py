"""Reports builder subsystem (PART 2/3) — real endpoints, real PostgreSQL + RLS.

Proves: allow-listed config rejects unknown sources/metrics (no arbitrary SQL), a saved
report persists + runs with correct package analytics, CSV export reflects DB values,
lifecycle (update/duplicate/archive), and a foreign tenant cannot see a saved report.
"""
import os
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from app.core.security import hash_token, new_opaque_token, utc_now
from app.db.session import SessionLocal
from app.db.tenant import set_tenant_context
from app.modules.reports import routes as rep
from app.modules.reports.schemas import ReportConfig, SavedReportCreate, SavedReportDuplicate, SavedReportUpdate

pytestmark = pytest.mark.integration

CSRF = "c" * 32


def _req():
    return SimpleNamespace(headers={"origin": "http://localhost:3000"}, state=SimpleNamespace(request_id=str(uuid4())))


def _admin():
    if not os.getenv("TEST_ADMIN_DATABASE_URL") or not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("PostgreSQL integration URLs are not configured")
    return create_engine(os.getenv("TEST_ADMIN_DATABASE_URL"))


def test_report_config_rejects_non_allowlisted_input() -> None:
    # No arbitrary SQL: unknown source / metric / dimension / filter all fail validation.
    with pytest.raises(ValueError):
        ReportConfig(source="evil_table", metrics=["count"])
    with pytest.raises(ValueError):
        ReportConfig(source="package_sales", metrics=["count); DROP TABLE patient_packages;--"])
    with pytest.raises(ValueError):
        ReportConfig(source="package_sales", metrics=["count"], group_by=["passwords"])
    with pytest.raises(ValueError):
        ReportConfig(source="package_sales", metrics=["count"], filters={"secret": "x"})


def test_package_financials_distinguishes_invoiced_collected_refunds() -> None:
    admin = _admin()
    clinic, user, patient, pkg, invoice = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    token = new_opaque_token()
    now = utc_now()
    try:
        with admin.begin() as c:
            c.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:id, 'Fin Clinic', :slug)"), {"id": clinic, "slug": f"fin-{clinic}"})
            c.execute(text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, status) VALUES (:id, :c, :e, 'Mgr', 'x', 'active')"), {"id": user, "c": clinic, "e": f"m-{user}@t.local"})
            c.execute(text("INSERT INTO user_roles (clinic_id, user_id, role_id) SELECT :c, :u, r.id FROM roles r WHERE r.name='manager' AND r.clinic_id IS NULL"), {"c": clinic, "u": user})
            c.execute(text("INSERT INTO patients (id, clinic_id, patient_number, full_name) VALUES (:id, :c, 'P-1', 'Fin Patient')"), {"id": patient, "c": clinic})
            c.execute(text("INSERT INTO invoices (id, clinic_id, patient_id, invoice_number, currency, total_minor, status, created_by_user_id) VALUES (:id, :c, :p, :num, 'USD', 10000, 'partially_paid', :u)"), {"id": invoice, "c": clinic, "p": patient, "num": f"INV-{invoice}", "u": user})
            c.execute(text("INSERT INTO payments (clinic_id, invoice_id, amount_minor, currency, method, recorded_by_user_id) VALUES (:c, :i, 6000, 'USD', 'cash', :u)"), {"c": clinic, "i": invoice, "u": user})
            c.execute(text("INSERT INTO refunds (clinic_id, invoice_id, amount_minor, currency, reason, method, refunded_by_user_id) VALUES (:c, :i, 1000, 'USD', 'overcharge', 'cash', :u)"), {"c": clinic, "i": invoice, "u": user})
            c.execute(text("INSERT INTO package_definitions (id, clinic_id, name, total_price_minor, currency, validity_days) VALUES (:id, :c, 'Fin Bundle', 10000, 'USD', 30)"), {"id": pkg, "c": clinic})
            c.execute(text("INSERT INTO patient_packages (clinic_id, patient_id, package_definition_id, invoice_id, expires_at, total_sessions, used_sessions, status) VALUES (:c, :p, :pk, :inv, :exp, 3, 1, 'active')"), {"c": clinic, "p": patient, "pk": pkg, "inv": invoice, "exp": now + timedelta(days=30)})
            c.execute(text("""INSERT INTO sessions (user_id, token_hash, csrf_token_hash, mfa_verified, ip_hash, idle_expires_at, absolute_expires_at)
                              VALUES (:u, :th, :ch, true, 'x', :idle, :abs)"""),
                      {"u": user, "th": hash_token(token), "ch": hash_token(CSRF), "idle": now + timedelta(hours=2), "abs": now + timedelta(days=1)})

        db = SessionLocal()
        try:
            cfg = ReportConfig(source="package_financials", metrics=["count", "invoiced_minor", "collected_minor", "refunds_minor", "net_collected_minor", "sessions_purchased", "sessions_used"], range_preset="30d")
            row = rep.report_run_adhoc(cfg, _req(), db, token)["data"]["rows"][0]
            assert row["count"] == 1
            assert row["invoiced_minor"] == 10000   # from invoices.total_minor
            assert row["collected_minor"] == 6000   # payments only (not the invoice face value)
            assert row["refunds_minor"] == 1000
            assert row["net_collected_minor"] == 5000  # collected - refunds
            assert row["sessions_purchased"] == 3 and row["sessions_used"] == 1
        finally:
            db.close()
    finally:
        with admin.begin() as c:
            c.execute(text("DELETE FROM patient_packages WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM package_definitions WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM refunds WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM payments WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM invoices WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM patients WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM sessions WHERE user_id = :u"), {"u": user})
            c.execute(text("DELETE FROM user_roles WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM users WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM clinics WHERE id = :c"), {"c": clinic})


def test_saved_report_lifecycle_and_package_analytics() -> None:
    admin = _admin()
    clinic, user, patient, pkg = uuid4(), uuid4(), uuid4(), uuid4()
    token = new_opaque_token()
    now = utc_now()
    try:
        with admin.begin() as c:
            c.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:id, 'Rep Clinic', :slug)"), {"id": clinic, "slug": f"rep-{clinic}"})
            c.execute(text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, status) VALUES (:id, :c, :e, 'Manager', 'x', 'active')"), {"id": user, "c": clinic, "e": f"mgr-{user}@t.local"})
            c.execute(text("INSERT INTO user_roles (clinic_id, user_id, role_id) SELECT :c, :u, r.id FROM roles r WHERE r.name='manager' AND r.clinic_id IS NULL"), {"c": clinic, "u": user})
            c.execute(text("INSERT INTO patients (id, clinic_id, patient_number, full_name) VALUES (:id, :c, 'P-1', 'Rep Patient')"), {"id": patient, "c": clinic})
            c.execute(text("INSERT INTO package_definitions (id, clinic_id, name, total_price_minor, currency, validity_days) VALUES (:id, :c, 'Bundle', 8000, 'USD', 30)"), {"id": pkg, "c": clinic})
            c.execute(text("INSERT INTO patient_packages (clinic_id, patient_id, package_definition_id, expires_at, total_sessions, used_sessions, status) VALUES (:c, :p, :pk, :exp, 3, 1, 'active')"), {"c": clinic, "p": patient, "pk": pkg, "exp": now + timedelta(days=30)})
            c.execute(text("""INSERT INTO sessions (user_id, token_hash, csrf_token_hash, mfa_verified, ip_hash, idle_expires_at, absolute_expires_at)
                              VALUES (:u, :th, :ch, true, 'x', :idle, :abs)"""),
                      {"u": user, "th": hash_token(token), "ch": hash_token(CSRF), "idle": now + timedelta(hours=2), "abs": now + timedelta(days=1)})

        db = SessionLocal()
        try:
            cfg = ReportConfig(source="package_sales", metrics=["count", "sessions_purchased", "sessions_used", "sessions_remaining"], range_preset="30d")
            # ad-hoc preview reflects the seeded package
            adhoc = rep.report_run_adhoc(cfg, _req(), db, token)["data"]
            assert adhoc["rows"][0]["count"] == 1
            assert adhoc["rows"][0]["sessions_purchased"] == 3 and adhoc["rows"][0]["sessions_used"] == 1
            assert adhoc["rows"][0]["sessions_remaining"] == 2

            created = rep.report_create(SavedReportCreate(name="Pkg utilization", description="monthly", config=cfg), _req(), db, token, CSRF)["data"]
            rid = created["id"]
            assert created["source"] == "package_sales" and created["version"] == 1

            got = rep.report_get(rid, _req(), db, token)["data"]
            assert got["config"]["source"] == "package_sales"

            ran = rep.report_run_saved(rid, _req(), db, token)["data"]
            assert ran["rows"][0]["sessions_purchased"] == 3 and ran["report"]["id"] == rid

            listed = rep.report_list(_req(), db, token)["data"]
            assert any(r["id"] == rid for r in listed)

            updated = rep.report_update(rid, SavedReportUpdate(name="Pkg utilization v2", expected_version=created["version"]), _req(), db, token, CSRF)["data"]
            assert updated["name"] == "Pkg utilization v2" and updated["version"] == 2

            dup = rep.report_duplicate(rid, SavedReportDuplicate(name="Pkg utilization copy"), _req(), db, token, CSRF)["data"]
            assert dup["id"] != rid and dup["source"] == "package_sales"

            csv_body = rep.report_export_csv(rid, _req(), db, token).body.decode()
            assert "Packages sold" in csv_body and "Sessions purchased" in csv_body

            rep.report_archive(rid, _req(), db, token, CSRF)
            after = rep.report_list(_req(), db, token)["data"]
            assert not any(r["id"] == rid for r in after)  # archived hidden; duplicate still active
            assert any(r["id"] == dup["id"] for r in after)

            # foreign tenant cannot see this clinic's saved reports (DB-level RLS)
            set_tenant_context(db, uuid4())
            assert db.execute(text("SELECT COUNT(*) FROM saved_reports WHERE id = :id"), {"id": dup["id"]}).scalar_one() == 0
            db.rollback()
        finally:
            db.close()
    finally:
        with admin.begin() as c:
            c.execute(text("DELETE FROM saved_reports WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM patient_packages WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM package_definitions WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM patients WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM sessions WHERE user_id = :u"), {"u": user})
            c.execute(text("DELETE FROM user_roles WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM users WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM clinics WHERE id = :c"), {"c": clinic})

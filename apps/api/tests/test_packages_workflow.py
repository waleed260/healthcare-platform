"""Packages backend workflow (PART 1) — real endpoints, real PostgreSQL + RLS.

Drives create → add service → detail → edit → deactivate/activate → sell (with
idempotency) → consume → exhaust → overview as a clinic 'owner', and checks a
foreign tenant cannot see the package. Business + financial-integrity focused.
"""
import os
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.core.security import hash_token, new_opaque_token, utc_now
from app.db.session import SessionLocal
from app.db.tenant import set_tenant_context
from app.modules.packages import routes as pkg
from app.modules.packages.schemas import (
    PackageConsume, PackageCreate, PackagePayment, PackagePurchase, PackageServiceCreate,
    PackageStatusUpdate, PackageUpdate,
)

pytestmark = pytest.mark.integration

CSRF = "c" * 32


def _req():
    return SimpleNamespace(headers={"origin": "http://localhost:3000"}, state=SimpleNamespace(request_id=str(uuid4())))


def _admin():
    if not os.getenv("TEST_ADMIN_DATABASE_URL") or not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("PostgreSQL integration URLs are not configured")
    return create_engine(os.getenv("TEST_ADMIN_DATABASE_URL"))


def test_packages_full_workflow() -> None:
    admin = _admin()
    clinic, user, patient, service = uuid4(), uuid4(), uuid4(), uuid4()
    token = new_opaque_token()
    now = utc_now()
    try:
        with admin.begin() as c:
            c.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:id, 'Pkg Clinic', :slug)"), {"id": clinic, "slug": f"pkg-{clinic}"})
            c.execute(text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, status) VALUES (:id, :c, :e, 'Manager', 'x', 'active')"), {"id": user, "c": clinic, "e": f"mgr-{user}@t.local"})
            # 'manager' holds the same package.* permissions as owner (migration 0050) but
            # is not subject to the last-active-owner trigger, keeping teardown clean.
            c.execute(text("INSERT INTO user_roles (clinic_id, user_id, role_id) SELECT :c, :u, r.id FROM roles r WHERE r.name='manager' AND r.clinic_id IS NULL"), {"c": clinic, "u": user})
            c.execute(text("INSERT INTO services (id, clinic_id, name, duration_minutes) VALUES (:id, :c, 'Laser', 30)"), {"id": service, "c": clinic})
            c.execute(text("INSERT INTO patients (id, clinic_id, patient_number, full_name) VALUES (:id, :c, 'P-1', 'Pkg Patient')"), {"id": patient, "c": clinic})
            c.execute(text("""INSERT INTO sessions (user_id, token_hash, csrf_token_hash, mfa_verified, ip_hash, idle_expires_at, absolute_expires_at)
                              VALUES (:u, :th, :ch, true, 'x', :idle, :abs)"""),
                      {"u": user, "th": hash_token(token), "ch": hash_token(CSRF), "idle": now + timedelta(hours=2), "abs": now + timedelta(days=1)})

        db = SessionLocal()
        try:
            # create + add a service with 2 sessions
            created = pkg.package_create(PackageCreate(name="Starter", total_price_minor=8000, original_value_minor=10000, currency="usd", validity_days=30), _req(), db, token, CSRF)["data"]
            pid = created["id"]
            assert created["currency"] == "USD" and created["status"] == "active"
            pkg.package_service_add(pid, PackageServiceCreate(service_id=service, sessions_count=2), _req(), db, token, CSRF)

            detail = pkg.package_detail(pid, _req(), db, token)["data"]
            assert detail["total_sessions"] == 2 and len(detail["services"]) == 1 and detail["sold"]["total_sold"] == 0

            # edit savings validation: original must be >= total (endpoint returns 400)
            with pytest.raises(HTTPException) as bad:
                pkg.package_update(pid, PackageUpdate(total_price_minor=12000, original_value_minor=10000, expected_version=created["version"]), _req(), db, token, CSRF)
            assert bad.value.status_code == 400
            db.rollback()
            edited = pkg.package_update(pid, PackageUpdate(name="Starter Plus", expected_version=created["version"]), _req(), db, token, CSRF)["data"]
            assert edited["name"] == "Starter Plus" and edited["version"] == created["version"] + 1

            # deactivate -> cannot be sold (explicit 409 with a reason, not a bare 404)
            deact = pkg.package_status(pid, PackageStatusUpdate(action="deactivate", expected_version=edited["version"]), _req(), db, token, CSRF)["data"]
            assert deact["status"] == "inactive"
            with pytest.raises(HTTPException) as exc:
                pkg.package_purchase(pid, PackagePurchase(patient_id=patient), _req(), db, token, CSRF)
            assert exc.value.status_code == 409
            # deactivating twice is reported, and does not bump the version
            with pytest.raises(HTTPException) as again_conflict:
                pkg.package_status(pid, PackageStatusUpdate(action="deactivate", expected_version=deact["version"]), _req(), db, token, CSRF)
            assert again_conflict.value.status_code == 409
            assert again_conflict.value.detail["error"]["code"] == "INVALID_STATE"
            db.rollback()
            react = pkg.package_status(pid, PackageStatusUpdate(action="activate", expected_version=deact["version"]), _req(), db, token, CSRF)["data"]
            assert react["status"] == "active"

            # sell with idempotency — repeat returns the SAME purchase, no duplicate
            key = uuid4()
            first = pkg.package_purchase(pid, PackagePurchase(patient_id=patient, idempotency_key=key), _req(), db, token, CSRF)["data"]
            again = pkg.package_purchase(pid, PackagePurchase(patient_id=patient, idempotency_key=key), _req(), db, token, CSRF)["data"]
            assert first["id"] == again["id"] and first["total_sessions"] == 2 and first["used_sessions"] == 0

            # consume both sessions -> exhausted; third rejected without override
            pkg.package_consume(first["id"], PackageConsume(service_id=service), _req(), db, token, CSRF)
            pkg.package_consume(first["id"], PackageConsume(service_id=service), _req(), db, token, CSRF)
            after = pkg.patient_purchase_detail(first["id"], _req(), db, token)["data"]
            assert after["used_sessions"] == 2 and after["remaining_sessions"] == 0 and after["status"] == "exhausted"
            assert sum(1 for s in after["sessions"] if s["status"] == "used") == 2
            with pytest.raises(HTTPException) as exc2:
                pkg.package_consume(first["id"], PackageConsume(service_id=service), _req(), db, token, CSRF)
            assert exc2.value.status_code == 409
            db.rollback()

            overview = pkg.package_overview(_req(), db, token)["data"]
            assert overview["total_sold"] == 1 and overview["sessions_purchased"] == 2 and overview["sessions_used"] == 2 and overview["sessions_remaining"] == 0

            # exactly one purchase persisted despite the duplicate sell request
            db.execute(text("SELECT set_config('app.clinic_id', :c, true)"), {"c": str(clinic)})
            assert db.execute(text("SELECT COUNT(*) FROM patient_packages WHERE clinic_id = :c AND patient_id = :p"), {"c": clinic, "p": patient}).scalar_one() == 1
            # a foreign tenant context cannot see this clinic's package (DB-level RLS)
            set_tenant_context(db, uuid4())
            assert db.execute(text("SELECT COUNT(*) FROM package_definitions WHERE id = :id"), {"id": pid}).scalar_one() == 0
            db.rollback()
        finally:
            db.close()
    finally:
        with admin.begin() as c:
            for tbl in ("package_sessions", "patient_packages", "package_services", "package_definitions"):
                c.execute(text(f"DELETE FROM {tbl} WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM patients WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM services WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM sessions WHERE user_id = :u"), {"u": user})
            c.execute(text("DELETE FROM user_roles WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM users WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM clinics WHERE id = :c"), {"c": clinic})


def test_sell_creates_invoice_and_records_payment() -> None:
    """Sell -> create invoice -> record payment, atomically. Paid invoice reads 'paid';
    an invoice sold without payment stays 'unpaid' and is never counted as collected."""
    admin = _admin()
    clinic, user, patient, service, pkgid = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    token = new_opaque_token()
    now = utc_now()
    try:
        with admin.begin() as c:
            c.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:id, 'Sell Clinic', :slug)"), {"id": clinic, "slug": f"sell-{clinic}"})
            c.execute(text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, status) VALUES (:id, :c, :e, 'Mgr', 'x', 'active')"), {"id": user, "c": clinic, "e": f"s-{user}@t.local"})
            c.execute(text("INSERT INTO user_roles (clinic_id, user_id, role_id) SELECT :c, :u, r.id FROM roles r WHERE r.name='manager' AND r.clinic_id IS NULL"), {"c": clinic, "u": user})
            c.execute(text("INSERT INTO services (id, clinic_id, name, duration_minutes) VALUES (:id, :c, 'Laser', 30)"), {"id": service, "c": clinic})
            c.execute(text("INSERT INTO patients (id, clinic_id, patient_number, full_name) VALUES (:id, :c, 'P-1', 'Sell Patient')"), {"id": patient, "c": clinic})
            c.execute(text("INSERT INTO package_definitions (id, clinic_id, name, total_price_minor, currency, validity_days) VALUES (:id, :c, 'Bundle', 10000, 'USD', 30)"), {"id": pkgid, "c": clinic})
            c.execute(text("INSERT INTO package_services (clinic_id, package_definition_id, service_id, sessions_count) VALUES (:c, :pk, :s, 2)"), {"c": clinic, "pk": pkgid, "s": service})
            c.execute(text("""INSERT INTO sessions (user_id, token_hash, csrf_token_hash, mfa_verified, ip_hash, idle_expires_at, absolute_expires_at)
                              VALUES (:u, :th, :ch, true, 'x', :idle, :abs)"""),
                      {"u": user, "th": hash_token(token), "ch": hash_token(CSRF), "idle": now + timedelta(hours=2), "abs": now + timedelta(days=1)})

        db = SessionLocal()
        try:
            paid = pkg.package_purchase(pkgid, PackagePurchase(patient_id=patient, create_invoice=True, payment=PackagePayment(amount_minor=10000, method="cash"), idempotency_key=uuid4()), _req(), db, token, CSRF)["data"]
            assert paid["invoice_id"] is not None and paid["invoice_status"] == "paid"
            db.execute(text("SELECT set_config('app.clinic_id', :c, true)"), {"c": str(clinic)})
            inv = db.execute(text("SELECT status, total_minor FROM invoices WHERE clinic_id=:c AND id=:i"), {"c": clinic, "i": paid["invoice_id"]}).mappings().one()
            assert inv["status"] == "paid" and inv["total_minor"] == 10000
            assert db.execute(text("SELECT COALESCE(SUM(amount_minor),0) FROM payments WHERE clinic_id=:c AND invoice_id=:i"), {"c": clinic, "i": paid["invoice_id"]}).scalar_one() == 10000
            db.rollback()

            unpaid = pkg.package_purchase(pkgid, PackagePurchase(patient_id=patient, create_invoice=True, idempotency_key=uuid4()), _req(), db, token, CSRF)["data"]
            assert "invoice_status" not in unpaid and unpaid["invoice_id"] is not None
            db.execute(text("SELECT set_config('app.clinic_id', :c, true)"), {"c": str(clinic)})
            assert db.execute(text("SELECT status FROM invoices WHERE clinic_id=:c AND id=:i"), {"c": clinic, "i": unpaid["invoice_id"]}).scalar_one() == "unpaid"
            assert db.execute(text("SELECT COALESCE(SUM(amount_minor),0) FROM payments WHERE clinic_id=:c AND invoice_id=:i"), {"c": clinic, "i": unpaid["invoice_id"]}).scalar_one() == 0
            db.rollback()
        finally:
            db.close()
    finally:
        with admin.begin() as c:
            for tbl in ("payment_allocations", "payments", "package_sessions", "patient_packages", "invoice_lines", "invoices", "invoice_number_sequences", "package_services", "package_definitions"):
                c.execute(text(f"DELETE FROM {tbl} WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM services WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM patients WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM sessions WHERE user_id = :u"), {"u": user})
            c.execute(text("DELETE FROM user_roles WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM users WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM clinics WHERE id = :c"), {"c": clinic})


def test_create_with_services_delete_and_override() -> None:
    """Create a sellable package in one request, then exercise safe delete, the
    delete-blocked-by-history path, idempotency-key conflicts and an authorised overuse."""
    admin = _admin()
    clinic, user, patient, service = uuid4(), uuid4(), uuid4(), uuid4()
    token = new_opaque_token()
    now = utc_now()
    try:
        with admin.begin() as c:
            c.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:id, 'Del Clinic', :slug)"), {"id": clinic, "slug": f"del-{clinic}"})
            c.execute(text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, status) VALUES (:id, :c, :e, 'Mgr', 'x', 'active')"), {"id": user, "c": clinic, "e": f"d-{user}@t.local"})
            c.execute(text("INSERT INTO user_roles (clinic_id, user_id, role_id) SELECT :c, :u, r.id FROM roles r WHERE r.name='manager' AND r.clinic_id IS NULL"), {"c": clinic, "u": user})
            c.execute(text("INSERT INTO services (id, clinic_id, name, duration_minutes) VALUES (:id, :c, 'Laser', 30)"), {"id": service, "c": clinic})
            c.execute(text("INSERT INTO patients (id, clinic_id, patient_number, full_name) VALUES (:id, :c, 'P-1', 'Del Patient')"), {"id": patient, "c": clinic})
            c.execute(text("""INSERT INTO sessions (user_id, token_hash, csrf_token_hash, mfa_verified, ip_hash, idle_expires_at, absolute_expires_at)
                              VALUES (:u, :th, :ch, true, 'x', :idle, :abs)"""),
                      {"u": user, "th": hash_token(token), "ch": hash_token(CSRF), "idle": now + timedelta(hours=2), "abs": now + timedelta(days=1)})

        db = SessionLocal()
        try:
            # 1) create + included services in one transaction -> immediately sellable
            created = pkg.package_create(
                PackageCreate(name="One Shot", total_price_minor=5000, currency="pkr", validity_days=10,
                              services=[PackageServiceCreate(service_id=service, sessions_count=1)]),
                _req(), db, token, CSRF)["data"]
            assert created["total_sessions"] == 1
            assert pkg.package_detail(created["id"], _req(), db, token)["data"]["total_sessions"] == 1

            # 2) an unsold package can be hard-deleted
            assert pkg.package_delete(created["id"], _req(), db, token, CSRF)["data"]["deleted"] is True
            with pytest.raises(HTTPException) as gone:
                pkg.package_detail(created["id"], _req(), db, token)
            assert gone.value.status_code == 404

            # 3) sell it, then deletion must be blocked with a safe archive hint
            sellable = pkg.package_create(
                PackageCreate(name="One Shot", total_price_minor=5000, currency="pkr", validity_days=10,
                              services=[PackageServiceCreate(service_id=service, sessions_count=1)]),
                _req(), db, token, CSRF)["data"]
            key = uuid4()
            sold = pkg.package_purchase(sellable["id"], PackagePurchase(patient_id=patient, idempotency_key=key), _req(), db, token, CSRF)["data"]
            with pytest.raises(HTTPException) as blocked:
                pkg.package_delete(sellable["id"], _req(), db, token, CSRF)
            assert blocked.value.status_code == 409
            assert blocked.value.detail["error"]["code"] == "PACKAGE_IN_USE"
            # ...and the sale + ledger survived the refused delete
            db.execute(text("SELECT set_config('app.clinic_id', :c, true)"), {"c": str(clinic)})
            assert db.execute(text("SELECT COUNT(*) FROM patient_packages WHERE clinic_id = :c AND id = :p"), {"c": clinic, "p": sold["id"]}).scalar_one() == 1
            assert db.execute(text("SELECT COUNT(*) FROM package_sessions WHERE clinic_id = :c AND patient_package_id = :p"), {"c": clinic, "p": sold["id"]}).scalar_one() == 1
            db.rollback()

            # 4) an idempotency key already used for a different package is a conflict
            other = pkg.package_create(
                PackageCreate(name="Other", total_price_minor=1000, currency="pkr", validity_days=10,
                              services=[PackageServiceCreate(service_id=service, sessions_count=1)]),
                _req(), db, token, CSRF)["data"]
            with pytest.raises(HTTPException) as reuse:
                pkg.package_purchase(other["id"], PackagePurchase(patient_id=patient, idempotency_key=key), _req(), db, token, CSRF)
            assert reuse.value.status_code == 409
            assert reuse.value.detail["error"]["code"] == "IDEMPOTENCY_CONFLICT"
            db.rollback()

            # 5) an authorised overuse is written to the ledger without breaking the
            #    used_sessions <= total_sessions database check
            pkg.package_consume(sold["id"], PackageConsume(service_id=service), _req(), db, token, CSRF)
            over = pkg.package_consume(sold["id"], PackageConsume(service_id=service, override_reason="clinically approved extra"), _req(), db, token, CSRF)["data"]
            assert over["status"] == "overuse_override"
            detail = pkg.patient_purchase_detail(sold["id"], _req(), db, token)["data"]
            assert detail["used_sessions"] == 1 and detail["status"] == "exhausted"
            assert sum(1 for s in detail["sessions"] if s["status"] == "overuse_override") == 1
        finally:
            db.close()
    finally:
        with admin.begin() as c:
            for tbl in ("payment_allocations", "payments", "package_sessions", "patient_packages", "invoice_lines", "invoices", "invoice_number_sequences", "package_services", "package_definitions"):
                c.execute(text(f"DELETE FROM {tbl} WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM services WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM patients WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM sessions WHERE user_id = :u"), {"u": user})
            c.execute(text("DELETE FROM user_roles WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM users WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM clinics WHERE id = :c"), {"c": clinic})

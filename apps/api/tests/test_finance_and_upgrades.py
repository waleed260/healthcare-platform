from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.main import app
from app.modules.finance.receipt import render_html, render_pdf
from app.modules.finance.schemas import ExpenseCreate
from app.modules.upgrades.schemas import UpgradeDecision, UpgradeRequestCreate

RECEIPT = {
    "clinic": {"name": "Smile <Clinic>"},
    "patient": {"id": uuid4(), "patient_number": "P-1", "name": "Ayesha (Khan)"},
    "invoice": {"invoice_number": "CLINIC-2026-000001", "currency": "PKR", "subtotal_minor": 1200000, "discount_minor": 0, "tax_minor": 0, "total_minor": 1200000, "paid_minor": 500000, "balance_minor": 700000, "status": "partially_paid", "issued_at": datetime(2026, 10, 2, 9, 30, tzinfo=timezone.utc), "notes": None},
    "lines": [{"description": "Root canal", "quantity": 1, "unit_price_minor": 1200000, "line_total_minor": 1200000}],
    "payments": [{"amount_minor": 500000, "method": "cash", "paid_at": datetime(2026, 10, 2, 9, 40, tzinfo=timezone.utc)}],
}


@pytest.mark.parametrize("fmt", ["a4", "thermal"])
def test_receipt_pdf_is_wellformed_and_sized(fmt: str) -> None:
    pdf = render_pdf(RECEIPT, fmt)
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    assert b"CLINIC-2026-000001" in pdf and b"BALANCE" in pdf
    assert (b"/MediaBox [0 0 227 " in pdf) == (fmt == "thermal")
    assert b"\\(Khan\\)" in pdf  # parentheses are escaped


def test_receipt_html_escapes_markup() -> None:
    page = render_html(RECEIPT, "thermal")
    assert "&lt;CLINIC&gt;" in page
    assert "<CLINIC>" not in page and "80mm" in page


def test_expense_validation() -> None:
    ExpenseCreate(category="rent", description="October rent", amount_minor=5000000, incurred_on=date(2026, 10, 1))
    with pytest.raises(ValidationError):
        ExpenseCreate(category="rent", description="x", amount_minor=0, incurred_on=date(2026, 10, 1))
    with pytest.raises(ValidationError):
        ExpenseCreate(category="bribes", description="x", amount_minor=1, incurred_on=date(2026, 10, 1))


def test_upgrade_schemas() -> None:
    UpgradeRequestCreate(kind="specialty", target_code="skin")
    with pytest.raises(ValidationError):
        UpgradeRequestCreate(kind="specialty", target_code="Skin; DROP")
    assert UpgradeDecision(decision="approve").note is None
    with pytest.raises(ValidationError):
        UpgradeDecision(decision="maybe")


def test_new_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])
    for expected in ("/api/v1/invoices/{invoice_id}/receipt.pdf", "/api/v1/invoices/{invoice_id}/receipt.html", "/api/v1/finance/cashier-summary", "/api/v1/finance/expenses", "/api/v1/upgrade-requests", "/api/v1/admin/upgrade-requests", "/api/v1/admin/overview"):
        assert expected in paths


def test_clinic_update_accepts_only_iso_style_currency() -> None:
    from app.modules.authorization.schemas import ClinicUpdate

    assert ClinicUpdate(expected_version=1, default_currency="USD").default_currency == "USD"
    for bad in ("usd", "US", "USDX", "12A"):
        with pytest.raises(ValidationError):
            ClinicUpdate(expected_version=1, default_currency=bad)

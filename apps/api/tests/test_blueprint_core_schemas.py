import pytest
from pydantic import ValidationError

from app.modules.blueprint_core.schemas import InvoiceCreate, LeadCreate, LeadUpdate, PaymentCreate, SpecialtyEnable


def test_specialty_enable_uses_safe_platform_code():
    assert SpecialtyEnable(code="skin_aesthetics").code == "skin_aesthetics"
    with pytest.raises(ValidationError):
        SpecialtyEnable(code="Skin Aesthetics")


def test_lead_create_is_strict_and_lead_update_requires_a_change():
    lead = LeadCreate(full_name="Prospect", source="website")
    assert lead.full_name == "Prospect"
    with pytest.raises(ValidationError):
        LeadCreate(full_name="Prospect", source="website", unsupported=True)
    with pytest.raises(ValidationError):
        LeadUpdate(expected_version=1)


def test_invoice_requires_at_least_one_line_and_payment_method():
    with pytest.raises(ValidationError):
        InvoiceCreate(patient_id="00000000-0000-0000-0000-000000000001", currency="PKR", lines=[])
    payment = PaymentCreate(amount_minor=1200, method="cash")
    assert payment.amount_minor == 1200

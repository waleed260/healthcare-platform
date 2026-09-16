from datetime import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.catalog.schemas import BranchCreate, BranchHoursUpsert, DoctorCreate, HolidayCreate, ResourceCreate
from app.modules.catalog import routes as catalog_routes


def test_branch_requires_a_valid_iana_timezone() -> None:
    branch = BranchCreate(code="north", name="Synthetic Branch", timezone="UTC")
    assert branch.timezone == "UTC"
    with pytest.raises(ValidationError):
        BranchCreate(code="north", name="Synthetic Branch", timezone="Not/AZone")


def test_hours_and_doctor_inputs_are_bounded() -> None:
    hours = BranchHoursUpsert(weekday=0, opens_at=time(9), closes_at=time(17))
    assert hours.weekday == 0
    assert DoctorCreate(public_name="Synthetic Clinician", consultation_duration_minutes=30).consultation_duration_minutes == 30
    with pytest.raises(ValidationError):
        BranchHoursUpsert(weekday=7, is_closed=True)
    assert HolidayCreate(holiday_date="2026-12-25", name="Synthetic closure").name
    assert HolidayCreate(holiday_date="2026-12-25", name="Synthetic branch closure", branch_id=uuid4(), starts_at=time(12), ends_at=time(13)).ends_at == time(13)
    with pytest.raises(ValidationError):
        HolidayCreate(holiday_date="2026-12-25", name="Synthetic invalid", starts_at=time(12))
    assert ResourceCreate(name="Synthetic resource").capacity == 1


def test_branch_scoped_catalog_authorization_passes_branch_scope(monkeypatch) -> None:
    calls = []
    session = {"clinic_id": "clinic-1", "user_id": "user-1"}

    monkeypatch.setattr(catalog_routes, "_session_or_401", lambda db, token: session)
    monkeypatch.setattr(catalog_routes, "set_tenant_context", lambda db, clinic_id, user_id: None)
    monkeypatch.setattr(
        catalog_routes,
        "require_permission",
        lambda db, user_id, clinic_id, permission, branch_id=None: calls.append((permission, branch_id)),
    )

    result = catalog_routes._authorized(SimpleNamespace(), "session", "branch.manage", branch_id="branch-1")

    assert result == session
    assert calls == [("branch.manage", "branch-1")]

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.clinical.schemas import TreatmentPlanCreate, TreatmentPlanItemCreate, TreatmentPlanItemUpdate


def test_treatment_plan_requires_title_and_patient() -> None:
    with pytest.raises(ValidationError):
        TreatmentPlanCreate(title="", patient_id=uuid4())


def test_treatment_plan_accepts_bounded_dates() -> None:
    plan = TreatmentPlanCreate(patient_id=uuid4(), title="Restoration", starts_on=date(2026, 1, 1), ends_on=date(2026, 2, 1))
    assert plan.ends_on > plan.starts_on


def test_treatment_item_status_is_bounded() -> None:
    item = TreatmentPlanItemCreate(title="Review", sort_order=2)
    assert item.sort_order == 2
    with pytest.raises(ValidationError):
        TreatmentPlanItemUpdate(expected_version=1, status="deleted")

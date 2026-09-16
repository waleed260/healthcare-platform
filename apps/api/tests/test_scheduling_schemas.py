import pytest
from pydantic import ValidationError

from app.modules.scheduling.schemas import AvailabilityRuleCreate, BlockedSlotCreate


def test_availability_rule_rejects_reversed_interval() -> None:
    with pytest.raises(ValidationError):
        AvailabilityRuleCreate(branch_id="00000000-0000-0000-0000-000000000001", doctor_id="00000000-0000-0000-0000-000000000002", weekday=1, starts_at="11:00", ends_at="10:00", effective_from="2026-01-01")


def test_blocked_slot_requires_timezone_aware_ordered_times() -> None:
    with pytest.raises(ValidationError):
        BlockedSlotCreate(branch_id="00000000-0000-0000-0000-000000000001", starts_at="2026-01-01T10:00:00", ends_at="2026-01-01T11:00:00", reason="Synthetic maintenance")

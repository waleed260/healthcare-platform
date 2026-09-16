from datetime import datetime, timezone
from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.modules.appointments.schemas import PublicCancelRequest, PublicRescheduleRequest
from app.modules.appointments.rate_limit import consume_public_management_limit


class _Scalar:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class _DB:
    def __init__(self, count):
        self.count = count
        self.sql = ""

    def execute(self, statement, params=None):
        self.sql = str(statement)
        return _Scalar(self.count)


def test_public_management_commands_require_reason() -> None:
    assert PublicCancelRequest(reason="Synthetic request").reason
    with pytest.raises(ValidationError):
        PublicCancelRequest(reason="")


def test_public_reschedule_requires_timezone_shape() -> None:
    item = PublicRescheduleRequest(starts_at=datetime(2026, 10, 1, 9, tzinfo=timezone.utc), reason="Synthetic request")
    assert item.starts_at.tzinfo is not None


def test_public_management_rate_limit_uses_serialized_fixed_window() -> None:
    db = _DB(20)
    assert consume_public_management_limit(db, clinic_id="clinic", reference="APT-1", ip_address="198.51.100.10")
    assert "ON CONFLICT (bucket_key) DO UPDATE" in db.sql

    db = _DB(21)
    assert not consume_public_management_limit(db, clinic_id="clinic", reference="APT-1", ip_address="198.51.100.10", window=timedelta(seconds=60))

from datetime import date, datetime, time, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.modules.appointments.availability import AvailabilityInterval, generate_slots
from app.modules.appointments.routes import _validate_availability_range


def test_slots_intersect_hours_and_exclude_buffer_overlap() -> None:
    interval = AvailabilityInterval(weekday=0, starts_at=time(9), ends_at=time(11))
    slots = generate_slots(start_date=date(2026, 9, 14), end_date=date(2026, 9, 14), timezone_name="UTC", branch_intervals=[interval], doctor_intervals=[interval], duration_minutes=30, buffer_after_minutes=15, busy_ranges=[(datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc), datetime(2026, 9, 14, 10, 30, tzinfo=timezone.utc))], minimum_notice=timedelta(0), now=datetime(2026, 9, 13, tzinfo=timezone.utc))
    assert datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc) in slots
    assert datetime(2026, 9, 14, 9, 45, tzinfo=timezone.utc) not in slots


def test_holidays_and_notice_are_applied() -> None:
    interval = AvailabilityInterval(weekday=1, starts_at=time(9), ends_at=time(10))
    slots = generate_slots(start_date=date(2026, 9, 15), end_date=date(2026, 9, 15), timezone_name="Asia/Karachi", branch_intervals=[interval], doctor_intervals=[interval], duration_minutes=30, holidays={date(2026, 9, 15)}, now=datetime(2026, 9, 14, tzinfo=timezone.utc))
    assert slots == []


def test_time_range_holiday_blocks_only_overlapping_slots() -> None:
    interval = AvailabilityInterval(weekday=0, starts_at=time(9), ends_at=time(12))
    slots = generate_slots(start_date=date(2026, 9, 14), end_date=date(2026, 9, 14), timezone_name="UTC", branch_intervals=[interval], doctor_intervals=[interval], duration_minutes=30, holiday_blocks=[(date(2026, 9, 14), time(10), time(11))], minimum_notice=timedelta(0), now=datetime(2026, 9, 13, tzinfo=timezone.utc))
    assert datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc) in slots
    assert datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc) not in slots


def test_public_availability_allows_ninety_day_horizon_but_rejects_longer() -> None:
    _validate_availability_range(date(2026, 1, 1), date(2026, 3, 31))
    with pytest.raises(HTTPException) as error:
        _validate_availability_range(date(2026, 1, 1), date(2026, 4, 2))
    assert error.value.status_code == 400


def test_repeated_dst_local_times_return_both_utc_instants() -> None:
    interval = AvailabilityInterval(weekday=6, starts_at=time(1), ends_at=time(2, 30))
    slots = generate_slots(start_date=date(2026, 11, 1), end_date=date(2026, 11, 1), timezone_name="America/New_York", branch_intervals=[interval], doctor_intervals=[interval], duration_minutes=30, minimum_notice=timedelta(0), now=datetime(2026, 10, 31, tzinfo=timezone.utc))
    assert datetime(2026, 11, 1, 5, 0, tzinfo=timezone.utc) in slots
    assert datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc) in slots


def test_repeated_dst_occupancy_follows_each_candidate_fold() -> None:
    interval = AvailabilityInterval(weekday=6, starts_at=time(1), ends_at=time(3), cadence_minutes=30)
    slots = generate_slots(start_date=date(2026, 11, 1), end_date=date(2026, 11, 1), timezone_name="America/New_York", branch_intervals=[interval], doctor_intervals=[interval], duration_minutes=30, minimum_notice=timedelta(0), now=datetime(2026, 10, 31, tzinfo=timezone.utc))
    assert slots == [
        datetime(2026, 11, 1, 5, 0, tzinfo=timezone.utc),
        datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc),
        datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc),
        datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc),
        datetime(2026, 11, 1, 7, 0, tzinfo=timezone.utc),
        datetime(2026, 11, 1, 7, 30, tzinfo=timezone.utc),
    ]


def test_nonexistent_dst_local_times_are_skipped() -> None:
    interval = AvailabilityInterval(weekday=6, starts_at=time(2), ends_at=time(3))
    slots = generate_slots(start_date=date(2026, 3, 8), end_date=date(2026, 3, 8), timezone_name="America/New_York", branch_intervals=[interval], doctor_intervals=[interval], duration_minutes=30, minimum_notice=timedelta(0), now=datetime(2026, 3, 7, tzinfo=timezone.utc))
    assert slots == []

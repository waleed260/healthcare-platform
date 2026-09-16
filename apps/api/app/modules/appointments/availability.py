from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class AvailabilityInterval:
    weekday: int
    starts_at: time
    ends_at: time
    effective_from: date = date.min
    effective_to: date | None = None
    cadence_minutes: int = 15


def _active(item: AvailabilityInterval, day: date) -> bool:
    return item.weekday == day.weekday() and item.effective_from <= day and (item.effective_to is None or day <= item.effective_to)


def _local_instants(local_value: datetime, zone: ZoneInfo) -> list[datetime]:
    """Resolve a local wall-clock value, preserving both DST folds and skipping gaps."""
    resolved: list[datetime] = []
    seen_utc: set[datetime] = set()
    for fold in (0, 1):
        candidate = local_value.replace(tzinfo=zone, fold=fold)
        round_trip = candidate.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
        candidate_utc = candidate.astimezone(timezone.utc)
        if round_trip == local_value and candidate_utc not in seen_utc:
            resolved.append(candidate)
            seen_utc.add(candidate_utc)
    return resolved


def _local_instant(local_value: datetime, zone: ZoneInfo, fold: int) -> datetime | None:
    """Resolve one wall-clock endpoint using the fold of its slot candidate."""
    instants = _local_instants(local_value, zone)
    if not instants:
        return None
    if len(instants) == 1:
        return instants[0]
    return next((value for value in instants if value.fold == fold), instants[0])


def generate_slots(*, start_date: date, end_date: date, timezone_name: str, branch_intervals: list[AvailabilityInterval], doctor_intervals: list[AvailabilityInterval], duration_minutes: int, buffer_before_minutes: int = 0, buffer_after_minutes: int = 0, busy_ranges: list[tuple[datetime, datetime]] | None = None, holidays: set[date] | None = None, holiday_blocks: list[tuple[date, time, time]] | None = None, minimum_notice: timedelta = timedelta(minutes=120), now: datetime | None = None) -> list[datetime]:
    """Intersect branch/doctor hours and return UTC starts whose occupancy is free."""
    if end_date < start_date or duration_minutes <= 0:
        return []
    zone = ZoneInfo(timezone_name)
    current_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    busy = busy_ranges or []
    closed = holidays or set()
    timed_closures = holiday_blocks or []
    slots: list[datetime] = []
    day = start_date
    while day <= end_date:
        if day not in closed:
            for branch in (item for item in branch_intervals if _active(item, day)):
                for doctor in (item for item in doctor_intervals if _active(item, day)):
                    window_start, window_end = max(branch.starts_at, doctor.starts_at), min(branch.ends_at, doctor.ends_at)
                    if window_start >= window_end:
                        continue
                    cadence = timedelta(minutes=max(1, doctor.cadence_minutes))
                    candidate_local = datetime.combine(day, window_start)
                    local_end = datetime.combine(day, window_end)
                    while candidate_local + timedelta(minutes=duration_minutes) <= local_end:
                        occupancy_start_local = candidate_local - timedelta(minutes=buffer_before_minutes)
                        occupancy_end_local = candidate_local + timedelta(minutes=duration_minutes + buffer_after_minutes)
                        blocked_by_timed_closure = any(day == closure_day and occupancy_start_local.time() < closure_end and occupancy_end_local.time() > closure_start for closure_day, closure_start, closure_end in timed_closures)
                        for candidate in _local_instants(candidate_local, zone):
                            candidate_utc = candidate.astimezone(timezone.utc)
                            occupancy_start = _local_instant(occupancy_start_local, zone, candidate.fold)
                            occupancy_end = _local_instant(occupancy_end_local, zone, candidate.fold)
                            if occupancy_start is None or occupancy_end is None:
                                continue
                            start_utc = occupancy_start.astimezone(timezone.utc)
                            end_utc = occupancy_end.astimezone(timezone.utc)
                            if start_utc >= end_utc:
                                continue
                            if candidate_utc >= current_utc + minimum_notice and not blocked_by_timed_closure and not any(start_utc < end and end_utc > start for start, end in busy):
                                slots.append(candidate_utc)
                        candidate_local += cadence
        day += timedelta(days=1)
    return sorted(set(slots))

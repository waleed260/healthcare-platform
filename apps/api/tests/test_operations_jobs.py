from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.modules.operations.jobs import overdue_job_key, retry_delay_seconds


def test_overdue_job_key_is_stable_and_utc_bound() -> None:
    task_id = uuid4()
    due_at = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
    assert overdue_job_key(task_id, due_at) == overdue_job_key(task_id, due_at)
    assert str(task_id) in overdue_job_key(task_id, due_at)


def test_job_key_does_not_contain_patient_content() -> None:
    assert "Synthetic" not in overdue_job_key(uuid4(), datetime.now(timezone.utc))


def test_retry_backoff_is_bounded_and_exponential() -> None:
    assert [retry_delay_seconds(attempt) for attempt in range(1, 4)] == [1, 2, 4]
    assert retry_delay_seconds(100) == 3600
    with pytest.raises(ValueError):
        retry_delay_seconds(0)

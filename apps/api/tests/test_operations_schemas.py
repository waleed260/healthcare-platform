from uuid import uuid4

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.modules.operations.schemas import FollowUpAssign, FollowUpComplete, FollowUpCreate, FollowUpUpdate, NotificationRead, PushSubscriptionCreate, QueueCheckIn, QueueCommand, QueueReorder


def test_queue_check_in_schema() -> None:
    item = QueueCheckIn(appointment_id=uuid4(), expected_version=1)
    assert item.expected_version == 1
    assert QueueCommand(expected_version=1).expected_version == 1
    assert QueueReorder(expected_version=1, priority=50).priority == 50
    with pytest.raises(ValidationError):
        QueueReorder(expected_version=1, priority=101)


def test_follow_up_schema_is_strict_and_bounded() -> None:
    item = FollowUpCreate(patient_id=uuid4(), reason="Synthetic reminder", due_at=datetime.now(timezone.utc))
    assert item.priority == "normal"
    with pytest.raises(ValidationError):
        FollowUpCreate(patient_id=uuid4(), reason="x", due_at=datetime.now(timezone.utc), priority="urgent")
    with pytest.raises(ValidationError):
        FollowUpComplete(expected_version=0)
    assert FollowUpUpdate(expected_version=1, priority="high").priority == "high"
    assert FollowUpAssign(expected_version=1).assignee_user_id is None
    with pytest.raises(ValidationError):
        FollowUpUpdate(expected_version=1)


def test_notification_read_requires_a_bounded_id_list() -> None:
    item = NotificationRead(notification_ids=[uuid4()])
    assert len(item.notification_ids) == 1
    with pytest.raises(ValidationError):
        NotificationRead(notification_ids=[])
    item = PushSubscriptionCreate(endpoint="https://push.example.test/endpoint", p256dh="public-key", auth="auth-secret")
    assert str(item.endpoint).startswith("https://")
    with pytest.raises(ValidationError):
        PushSubscriptionCreate(endpoint="http://push.example.test/endpoint", p256dh="public-key", auth="auth-secret")

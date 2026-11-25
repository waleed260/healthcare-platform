"""Event-driven lead stage changes shared by the lead routes and the appointment routes.

These helpers keep the lead pipeline in sync with real appointment events (booking, arrival,
cancellation/no-show) and record every stage change in ``lead_stage_history``. They run inside
the caller's already-opened, tenant-scoped transaction and are idempotent: each guards on the
exact source status so a replayed event (or an appointment progressing further) never produces a
duplicate stage event.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def create_lead_follow_up(
    db: Session, clinic_id, lead_id, *, description: str, due_at: datetime,
    assigned_to_user_id: UUID | None, created_by_user_id: UUID,
):
    """Insert an actionable follow-up task. Returns the new row id."""
    return db.execute(text("""
        INSERT INTO lead_follow_ups (clinic_id, lead_id, description, due_at, assigned_to_user_id, created_by_user_id)
        VALUES (:clinic_id, :lead_id, :description, :due_at, :assigned_to, :created_by)
        RETURNING id
    """), {
        "clinic_id": clinic_id, "lead_id": lead_id, "description": description, "due_at": due_at,
        "assigned_to": assigned_to_user_id, "created_by": created_by_user_id,
    }).scalar_one()


def record_lead_stage(
    db: Session, clinic_id, lead_id, from_status: str | None, to_status: str,
    actor_user_id: UUID | None, reason: str | None = None,
) -> None:
    db.execute(text("""
        INSERT INTO lead_stage_history (clinic_id, lead_id, from_status, to_status, actor_user_id, reason)
        VALUES (:clinic_id, :lead_id, :from_status, :to_status, :actor, :reason)
    """), {
        "clinic_id": clinic_id, "lead_id": lead_id, "from_status": from_status,
        "to_status": to_status, "actor": actor_user_id, "reason": reason,
    })


def _locked_lead_status(db: Session, clinic_id, lead_id) -> str | None:
    return db.execute(text(
        "SELECT status FROM leads WHERE clinic_id = :c AND id = :l AND archived_at IS NULL FOR UPDATE"
    ), {"c": clinic_id, "l": lead_id}).scalar_one_or_none()


def link_appointment_to_lead(db: Session, clinic_id, lead_id, actor_user_id: UUID | None) -> bool:
    """A pre-booking lead gains a real appointment -> move it to ``appointment_booked``.

    Only ``new``/``contacted``/``qualified`` advance; an already booked/visited/converted/lost
    lead is left untouched (so a second appointment never regresses the stage). Returns whether
    the stage moved. The lead<->appointment link itself lives on ``appointments.lead_id`` and is
    persisted by the caller regardless of this return value.
    """
    current = _locked_lead_status(db, clinic_id, lead_id)
    if current not in {"new", "contacted", "qualified"}:
        return False
    db.execute(text(
        "UPDATE leads SET status = 'appointment_booked', version = version + 1, updated_at = now() "
        "WHERE clinic_id = :c AND id = :l"
    ), {"c": clinic_id, "l": lead_id})
    record_lead_stage(db, clinic_id, lead_id, current, "appointment_booked", actor_user_id, "appointment booked")
    return True


def mark_lead_visited(db: Session, clinic_id, lead_id, actor_user_id: UUID | None) -> bool:
    """Authoritative attendance: a linked appointment reached ``arrived`` -> lead ``visited``.

    Fires exactly once (guarded on ``appointment_booked``); later appointment progress
    (waiting/in_consultation/completed) does not re-fire, and a lead already past booked is a no-op.
    """
    current = _locked_lead_status(db, clinic_id, lead_id)
    if current != "appointment_booked":
        return False
    db.execute(text(
        "UPDATE leads SET status = 'visited', version = version + 1, updated_at = now() "
        "WHERE clinic_id = :c AND id = :l"
    ), {"c": clinic_id, "l": lead_id})
    record_lead_stage(db, clinic_id, lead_id, current, "visited", actor_user_id, "patient arrived")
    return True


def revert_lead_if_no_active_appointment(
    db: Session, clinic_id, lead_id, actor_user_id: UUID | None, reason: str,
) -> bool:
    """A linked appointment was cancelled/no-showed. If the lead has no other active appointment,
    return it from ``appointment_booked`` to ``qualified`` so it re-enters the working pipeline.

    Never marks the lead lost or visited. A lead already visited/converted/lost is untouched.
    When it reverts, a dated follow-up task is queued so the prospect is not dropped.
    """
    lead = db.execute(text(
        "SELECT status, assigned_to_user_id FROM leads WHERE clinic_id = :c AND id = :l AND archived_at IS NULL FOR UPDATE"
    ), {"c": clinic_id, "l": lead_id}).mappings().one_or_none()
    if lead is None or lead["status"] != "appointment_booked":
        return False
    active = db.execute(text("""
        SELECT 1 FROM appointments
        WHERE clinic_id = :c AND lead_id = :l AND archived_at IS NULL
          AND status NOT IN ('cancelled', 'no_show', 'rescheduled', 'completed')
        LIMIT 1
    """), {"c": clinic_id, "l": lead_id}).scalar_one_or_none()
    if active is not None:
        return False
    db.execute(text(
        "UPDATE leads SET status = 'qualified', version = version + 1, updated_at = now() "
        "WHERE clinic_id = :c AND id = :l"
    ), {"c": clinic_id, "l": lead_id})
    record_lead_stage(db, clinic_id, lead_id, "appointment_booked", "qualified", actor_user_id, reason)
    if actor_user_id is not None:
        create_lead_follow_up(
            db, clinic_id, lead_id,
            description=f"Reschedule — {reason}",
            due_at=datetime.now(timezone.utc) + timedelta(days=1),
            assigned_to_user_id=lead["assigned_to_user_id"],
            created_by_user_id=actor_user_id,
        )
    return True

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.tenant import set_tenant_context

JOB_BATCH_SIZE = 500


def retry_delay_seconds(attempts: int, *, maximum: int = 3600) -> int:
    if attempts < 1:
        raise ValueError("attempts must be positive")
    return min(maximum, 2 ** min(attempts - 1, 12))


def claim_next_job(db: Session, clinic_id: UUID, *, job_type: str | None = None, now: datetime | None = None) -> dict | None:
    """Claim one ready or stale job with PostgreSQL row-level serialization."""
    current = now or datetime.now(timezone.utc)
    set_tenant_context(db, clinic_id)
    job_type_filter = "AND job_type = :job_type" if job_type is not None else ""
    parameters = {"clinic_id": clinic_id, "now": current, "stale_before": current - timedelta(minutes=5)}
    if job_type is not None:
        parameters["job_type"] = job_type
    row = db.execute(text(f"""
        SELECT id, clinic_id, job_key, job_type, status, attempts, available_at
        FROM background_jobs
        WHERE clinic_id = :clinic_id
          {job_type_filter}
          AND (
              (status IN ('queued', 'failed') AND available_at <= :now)
              OR (status = 'running' AND locked_at < :stale_before)
          )
        ORDER BY available_at, created_at, id
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    """), parameters).mappings().one_or_none()
    if row is None:
        return None
    claimed = db.execute(text("""
        UPDATE background_jobs
        SET status = 'running', locked_at = :now, attempts = attempts + 1, updated_at = :now
        WHERE clinic_id = :clinic_id AND id = :id
        RETURNING id, clinic_id, job_key, job_type, status, attempts, available_at
    """), {"clinic_id": clinic_id, "id": row["id"], "now": current}).mappings().one()
    return dict(claimed)


def complete_job(db: Session, clinic_id: UUID, job_id: UUID) -> None:
    db.execute(text("""
        UPDATE background_jobs
        SET status = 'completed', locked_at = NULL, updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :id AND status = 'running'
    """), {"clinic_id": clinic_id, "id": job_id})


def fail_job(db: Session, clinic_id: UUID, job_id: UUID, *, attempts: int, failure_code: str, maximum_attempts: int = 5, now: datetime | None = None) -> None:
    """Requeue with bounded exponential backoff; persist only a safe failure code."""
    if maximum_attempts < 1 or attempts < 1:
        raise ValueError("attempt limits must be positive")
    current = now or datetime.now(timezone.utc)
    next_status = "failed" if attempts >= maximum_attempts else "queued"
    db.execute(text("""
        UPDATE background_jobs
        SET status = :status,
            available_at = CASE WHEN :status = 'queued' THEN :now + (:delay * interval '1 second') ELSE available_at END,
            locked_at = NULL,
            last_error = :failure_code,
            updated_at = :now
        WHERE clinic_id = :clinic_id AND id = :id AND status = 'running'
    """), {"clinic_id": clinic_id, "id": job_id, "status": next_status, "now": current, "delay": retry_delay_seconds(attempts), "failure_code": failure_code[:120]})


def overdue_job_key(task_id: UUID, due_at: datetime) -> str:
    return f"follow-up-overdue:{task_id}:{due_at.astimezone(timezone.utc).isoformat()}"


def run_overdue_follow_up_job(db: Session, clinic_id: UUID, now: datetime | None = None) -> int:
    """Create privacy-safe in-app notifications exactly once for overdue tasks."""
    current = now or datetime.now(timezone.utc)
    set_tenant_context(db, clinic_id)
    tasks = db.execute(text("""
        SELECT id, due_at, assignee_user_id
        FROM follow_up_tasks
        WHERE clinic_id = :clinic_id AND status IN ('due', 'contacted', 'booked') AND due_at < :now
        ORDER BY due_at, id
        LIMIT :batch_size
    """), {"clinic_id": clinic_id, "now": current, "batch_size": JOB_BATCH_SIZE}).mappings().all()
    created = 0
    for task in tasks:
        job_key = overdue_job_key(task["id"], task["due_at"])
        job = db.execute(text("""
            INSERT INTO background_jobs (clinic_id, job_key, job_type, status)
            VALUES (:clinic_id, :job_key, 'follow_up_overdue_notification', 'running')
            ON CONFLICT (clinic_id, job_key) DO NOTHING
            RETURNING id
        """), {"clinic_id": clinic_id, "job_key": job_key}).scalar_one_or_none()
        if job is None:
            continue
        recipients = db.execute(text("""
            SELECT DISTINCT ur.user_id
            FROM user_roles ur
            JOIN role_permissions rp ON rp.role_id = ur.role_id AND rp.permission_code = 'followup.read'
            WHERE ur.clinic_id = :clinic_id AND (:assignee IS NULL OR ur.user_id = :assignee)
        """), {"clinic_id": clinic_id, "assignee": task["assignee_user_id"]}).scalars().all()
        for user_id in recipients:
            result = db.execute(text("""
                INSERT INTO notifications (clinic_id, user_id, kind, title, body, source_job_key)
                VALUES (:clinic_id, :user_id, 'follow_up_overdue', 'Follow-up needs attention', 'A follow-up task is overdue. Open the dashboard to review it.', :job_key)
                ON CONFLICT (clinic_id, user_id, source_job_key) DO NOTHING
            """), {"clinic_id": clinic_id, "user_id": user_id, "job_key": job_key})
            created += result.rowcount
        db.execute(text("UPDATE background_jobs SET status = 'completed', updated_at = now() WHERE clinic_id = :clinic_id AND job_key = :job_key"), {"clinic_id": clinic_id, "job_key": job_key})
    db.commit()
    return created

"""Tenant-scoped background-job worker.

Run one worker per clinic (or have a trusted scheduler launch one per clinic).
The explicit clinic ID is intentional: a worker never discovers or iterates
tenants without an independently authorized orchestration layer.
"""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Callable
from uuid import UUID

from app.db.session import SessionLocal
from app.modules.files.jobs import run_next_document_metadata_encryption, run_next_stored_document_scan
from app.modules.governance.jobs import run_expired_artifact_cleanup, run_next_export_job
from app.modules.operations.jobs import run_overdue_follow_up_job
from app.modules.websites.scanner import run_next_stored_website_media_scan


LOGGER = logging.getLogger("healthcare.worker")
HANDLERS: dict[str, Callable] = {
    "document_scan": run_next_stored_document_scan,
    "document_metadata_encrypt": run_next_document_metadata_encryption,
    "website_media_scan": run_next_stored_website_media_scan,
    "export": run_next_export_job,
    "retention_cleanup": run_expired_artifact_cleanup,
}


def process_once(clinic_id: UUID, job_type: str) -> str | int | None:
    """Process at most one queued job, or one overdue-notification sweep."""
    if job_type == "follow_up_overdue_notification":
        with SessionLocal() as db:
            return run_overdue_follow_up_job(db, clinic_id)
    handler = HANDLERS[job_type]
    with SessionLocal() as db:
        return handler(db, clinic_id)


def worker_loop(clinic_id: UUID, job_type: str, poll_interval: float, once: bool) -> None:
    if poll_interval <= 0:
        raise ValueError("poll interval must be positive")
    while True:
        try:
            result = process_once(clinic_id, job_type)
            if result is not None:
                LOGGER.info("processed job type=%s result=%s", job_type, result)
        except Exception:
            # The individual job handlers persist bounded failure state. The
            # loop must remain alive for transient database/storage failures.
            LOGGER.exception("job processing failed type=%s", job_type)
        if once:
            return
        time.sleep(poll_interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clinic-id", required=True, type=UUID)
    parser.add_argument(
        "--job-type",
        choices=[*sorted(HANDLERS), "follow_up_overdue_notification"],
        default="document_scan",
    )
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--once", action="store_true", help="process once and exit")
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args()
    worker_loop(args.clinic_id, args.job_type, args.poll_interval, args.once)


if __name__ == "__main__":
    main()

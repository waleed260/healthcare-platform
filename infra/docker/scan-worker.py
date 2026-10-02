"""All-clinic background worker for the self-hosted Docker stack.

Drains queued scan jobs (patient media, website media, documents) for every active clinic, then
sweeps overdue follow-ups. Local-disk storage is shared with the API via a named volume, so the
API and this worker see the same files. Not used in CI; the API image already contains it.
"""
from __future__ import annotations

import logging
import os
import time

from sqlalchemy import text

from app.db.session import SessionLocal
from app.worker import process_once

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("healthcare.scan-worker")

SCAN_TYPES = ("patient_media_scan", "website_media_scan", "document_scan")
INTERVAL = float(os.environ.get("WORKER_POLL_SECONDS", "5"))
MAX_DRAIN = 50


def active_clinics() -> list:
    with SessionLocal() as db:
        return [row[0] for row in db.execute(text("SELECT id FROM clinics WHERE archived_at IS NULL"))]


def main() -> None:
    LOGGER.info("scan worker started (interval=%ss, types=%s)", INTERVAL, ",".join(SCAN_TYPES))
    while True:
        try:
            clinics = active_clinics()
        except Exception:
            LOGGER.exception("could not list clinics")
            time.sleep(INTERVAL)
            continue
        for clinic_id in clinics:
            for job_type in SCAN_TYPES:
                for _ in range(MAX_DRAIN):
                    try:
                        if process_once(clinic_id, job_type) is None:
                            break
                    except Exception:
                        LOGGER.exception("job failed clinic=%s type=%s", clinic_id, job_type)
                        break
            try:
                process_once(clinic_id, "follow_up_overdue_notification")
            except Exception:
                LOGGER.exception("follow-up sweep failed clinic=%s", clinic_id)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()

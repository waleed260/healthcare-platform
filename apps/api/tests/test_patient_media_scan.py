"""Patient-media scan pipeline on real Postgres + real local storage.

Covers the step beyond the HTTP upload: a stored object becomes 'clean' when its bytes match the
declared size/SHA/MIME, and 'scan_failed' when they do not. Approval requires scan_status='clean',
so this guards that gate. Runs against the runtime role with an explicit tenant context.
"""
import hashlib
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000b4944415478da6364f8cf00000302010965f6300000000049454e44ae426082"
)


def _session() -> Session:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("no runtime DB configured")
    return Session(create_engine(url))


def _insert_media(db: Session, clinic_id, patient, user, content, *, lie_size=False) -> str:
    from app.modules.files.storage import put_private_object

    media_id = uuid4()
    key = f"{clinic_id}/{patient}/{media_id}.png"
    put_private_object(key, content)
    db.execute(text("""
        INSERT INTO patient_media (id, clinic_id, patient_id, provider_user_id, media_kind, storage_key,
            original_filename, mime_type, size_bytes, content_sha256)
        VALUES (:id, :c, :p, :u, 'before', :key, 'x.png', 'image/png', :size, :sha)
    """), {"id": media_id, "c": clinic_id, "p": patient, "u": user, "key": key,
           "size": (len(content) + 1) if lie_size else len(content), "sha": hashlib.sha256(content).hexdigest()})
    db.execute(text("INSERT INTO background_jobs (clinic_id, job_key, job_type, status) VALUES (:c, :k, 'patient_media_scan', 'queued') ON CONFLICT (clinic_id, job_key) DO NOTHING"),
               {"c": clinic_id, "k": f"patient-media-scan:{media_id}"})
    return media_id


def test_valid_image_scans_clean_and_lying_size_fails() -> None:
    from app.modules.clinical_media.scanner import run_next_stored_patient_media_scan

    db = _session()
    created: list = []
    try:
        clinic_id = db.execute(text("SELECT id FROM clinics WHERE archived_at IS NULL ORDER BY created_at LIMIT 1")).scalar_one_or_none()
        if clinic_id is None:
            pytest.skip("no seeded clinic")
        db.execute(text("SELECT set_config('app.clinic_id', :c, true), set_config('app.user_id', :c, true)"), {"c": str(clinic_id)})
        patient = db.execute(text("SELECT id FROM patients WHERE clinic_id = :c LIMIT 1"), {"c": clinic_id}).scalar_one()
        user = db.execute(text("SELECT id FROM users WHERE clinic_id = :c LIMIT 1"), {"c": clinic_id}).scalar_one()
        good = _insert_media(db, clinic_id, patient, user, PNG)
        bad = _insert_media(db, clinic_id, patient, user, PNG, lie_size=True)
        created = [good, bad]
        db.commit()

        outcomes = []
        for _ in range(10):
            result = run_next_stored_patient_media_scan(db, clinic_id)
            if result is None:
                break
            outcomes.append(result)
        assert "clean" in outcomes and "scan_failed" in outcomes, outcomes
        statuses = dict(db.execute(text("SELECT id, scan_status FROM patient_media WHERE id = ANY(:ids)"), {"ids": created}).all())
        assert statuses[good] == "clean"
        assert statuses[bad] == "scan_failed"
    finally:
        if created:
            db.execute(text("DELETE FROM patient_media_scan_events WHERE media_id = ANY(:ids)"), {"ids": created})
            db.execute(text("DELETE FROM patient_media WHERE id = ANY(:ids)"), {"ids": created})
            db.execute(text("DELETE FROM background_jobs WHERE clinic_id = :c AND job_type = 'patient_media_scan'"), {"c": clinic_id})
            db.commit()
        db.close()

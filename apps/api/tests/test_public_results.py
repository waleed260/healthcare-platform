"""Public before/after gallery exposes ONLY approved, clean, consented media — on real Postgres.

Proves the privacy gate: approving makes media appear; revoking approval or withdrawing consent
removes it; pending/other-kind media never appears.
"""
import hashlib
import os
import types
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000b4944415478da6364f8cf00000302010965f6300000000049454e44ae426082")


def _session() -> Session:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("no runtime DB configured")
    return Session(create_engine(url))


def _req():
    return types.SimpleNamespace(state=types.SimpleNamespace(request_id=str(uuid4())))


def test_results_gallery_respects_approval_and_consent() -> None:
    from app.modules.clinical_media.public_routes import public_results
    from app.modules.files.storage import put_private_object

    db = _session()
    created_media: list = []
    consent_id = None
    try:
        row = db.execute(text("SELECT id, slug FROM clinics WHERE archived_at IS NULL AND status='active' ORDER BY created_at LIMIT 1")).first()
        if row is None:
            pytest.skip("no seeded clinic")
        clinic_id, slug = row
        db.execute(text("SELECT set_config('app.clinic_id', :c, true), set_config('app.user_id', :c, true)"), {"c": str(clinic_id)})
        patient = db.execute(text("SELECT id FROM patients WHERE clinic_id = :c LIMIT 1"), {"c": clinic_id}).scalar_one()
        user = db.execute(text("SELECT id FROM users WHERE clinic_id = :c LIMIT 1"), {"c": clinic_id}).scalar_one()
        consent_id = uuid4()
        db.execute(text("INSERT INTO consent_records (id, clinic_id, patient_id, consent_type, status, version, recorded_by_user_id) VALUES (:id,:c,:p,'website_media','granted','1',:u)"),
                   {"id": consent_id, "c": clinic_id, "p": patient, "u": user})
        # one approved before + after, one still-pending (must not show)
        for kind, approved in (("before", True), ("after", True), ("before", False)):
            mid = uuid4(); key = f"{clinic_id}/{patient}/{mid}.png"; put_private_object(key, PNG)
            db.execute(text("""
                INSERT INTO patient_media (id, clinic_id, patient_id, provider_user_id, media_kind, storage_key, original_filename,
                    mime_type, size_bytes, content_sha256, scan_status, approval_status, approved_for_website, consent_record_id)
                VALUES (:id,:c,:p,:u,:kind,:key,'x.png','image/png',:sz,:sha,
                    :scan, :astatus, :approved, :consent)
            """), {"id": mid, "c": clinic_id, "p": patient, "u": user, "kind": kind, "key": key, "sz": len(PNG),
                   "sha": hashlib.sha256(PNG).hexdigest(), "scan": "clean" if approved else "pending_scan",
                   "astatus": "approved" if approved else "pending", "approved": approved,
                   "consent": consent_id if approved else None})
            created_media.append(mid)
        db.commit()

        data = public_results(slug, _req(), db)["data"]
        kinds = sorted(m["media_kind"] for m in data)
        assert kinds == ["after", "before"], kinds          # pending excluded
        assert all(m["url"].endswith("/image") for m in data)
        assert len({m["case_ref"] for m in data}) == 1       # same patient -> one case
        assert not any("patient" in m for m in data)         # identity not leaked

        # revoke one approval -> only the other remains
        db.execute(text("SELECT set_config('app.clinic_id', :c, true), set_config('app.user_id', :c, true)"), {"c": str(clinic_id)})
        db.execute(text("UPDATE patient_media SET approved_for_website=false, approval_status='revoked' WHERE id=:id"), {"id": created_media[0]})
        db.commit()
        assert len(public_results(slug, _req(), db)["data"]) == 1

        # withdraw consent -> the remaining approved media disappears too
        db.execute(text("SELECT set_config('app.clinic_id', :c, true), set_config('app.user_id', :c, true)"), {"c": str(clinic_id)})
        db.execute(text("UPDATE consent_records SET status='withdrawn', withdrawn_at=now() WHERE id=:id"), {"id": consent_id})
        db.commit()
        assert public_results(slug, _req(), db)["data"] == []
    finally:
        try:
            db.execute(text("SELECT set_config('app.clinic_id', :c, true)"), {"c": str(clinic_id)})
        except Exception:
            pass
        if created_media:
            db.execute(text("DELETE FROM patient_media WHERE id = ANY(:ids)"), {"ids": created_media})
        if consent_id:
            db.execute(text("DELETE FROM consent_records WHERE id=:id"), {"id": consent_id})
        db.commit(); db.close()

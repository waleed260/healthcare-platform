"""Public before/after gallery: serves ONLY patient media approved for the website.

Every row must be approval_status='approved' AND approved_for_website=true AND scan_status='clean'
AND backed by a still-granted consent record. Revoking approval or withdrawing consent removes it
immediately. Patient identity is never exposed; before/after of one case share an opaque case_ref.
"""
from __future__ import annotations

import hashlib
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.files.storage import read_private_object
from app.modules.identity.routes import _error
from app.modules.websites.routes import _public_slug_clinic_id

public_router = APIRouter(prefix="/api/v1/public/sites/slug/{clinic_slug}", tags=["public-results"])

_APPROVED = (
    "pm.approved_for_website = true AND pm.approval_status = 'approved' "
    "AND pm.scan_status = 'clean' AND pm.archived_at IS NULL "
    "AND pm.media_kind IN ('before', 'after') "
    "AND c.status = 'granted' AND c.withdrawn_at IS NULL"
)


def _case_ref(clinic_id: UUID, patient_id) -> str:
    return hashlib.sha256(f"{clinic_id}:{patient_id}".encode()).hexdigest()[:12]


@public_router.get("/results")
def public_results(clinic_slug: str, request: Request, db: Session = Depends(get_db)) -> dict:
    clinic_id = _public_slug_clinic_id(db, clinic_slug)
    if clinic_id is None:
        raise _error("NOT_FOUND", "Website not found.", status.HTTP_404_NOT_FOUND)
    rows = db.execute(text(f"""
        SELECT pm.id, pm.patient_id, pm.media_kind, pm.captured_on
        FROM patient_media pm
        JOIN consent_records c ON c.clinic_id = pm.clinic_id AND c.id = pm.consent_record_id
        WHERE pm.clinic_id = :clinic_id AND {_APPROVED}
        ORDER BY pm.captured_on DESC, pm.id DESC
        LIMIT 60
    """), {"clinic_id": clinic_id}).mappings().all()
    items = [{
        "id": str(row["id"]),
        "media_kind": row["media_kind"],
        "captured_on": row["captured_on"].isoformat() if row["captured_on"] else None,
        "case_ref": _case_ref(clinic_id, row["patient_id"]),
        "url": f"/api/v1/public/sites/slug/{clinic_slug}/results/{row['id']}/image",
    } for row in rows]
    db.commit()
    # The gallery list is derived from live approval/consent state; keep it out of
    # shared caches so a withdrawn case cannot linger behind the image revocation.
    return {"data": items, "meta": {"request_id": request.state.request_id, "cache_control": "private, no-store"}}


@public_router.get("/results/{media_id}/image")
def public_result_image(clinic_slug: str, media_id: UUID, db: Session = Depends(get_db)) -> Response:
    clinic_id = _public_slug_clinic_id(db, clinic_slug)
    if clinic_id is None:
        raise _error("NOT_FOUND", "Image not found.", status.HTTP_404_NOT_FOUND)
    row = db.execute(text(f"""
        SELECT pm.storage_key, pm.mime_type
        FROM patient_media pm
        JOIN consent_records c ON c.clinic_id = pm.clinic_id AND c.id = pm.consent_record_id
        WHERE pm.clinic_id = :clinic_id AND pm.id = :media_id AND {_APPROVED}
    """), {"clinic_id": clinic_id, "media_id": media_id}).mappings().one_or_none()
    db.commit()
    if row is None:
        raise _error("NOT_FOUND", "Image not found.", status.HTTP_404_NOT_FOUND)
    try:
        content = read_private_object(row["storage_key"])
    except Exception as exc:
        raise _error("NOT_FOUND", "Image not found.", status.HTTP_404_NOT_FOUND) from exc
    # No shared/browser caching: approval or consent can be withdrawn at any time
    # and the module contract promises the image disappears immediately. A cached
    # copy (CDN or browser) would keep serving a revoked patient photo for the
    # life of the max-age, so patient media must never be stored downstream.
    return Response(content=content, media_type=row["mime_type"], headers={"Cache-Control": "private, no-store, max-age=0", "Vary": "Cookie"})

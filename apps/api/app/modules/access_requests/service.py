from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import hash_token
from app.modules.identity.service import create_staff_invitation, normalize_email


class AccessRequestError(RuntimeError):
    """Raised by the service layer; the route maps code/http_status to the API envelope."""

    def __init__(self, code: str, message: str, http_status: int):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


def resolve_clinic_id(db: Session, clinic_slug: str) -> UUID | None:
    """Resolve a public clinic slug to its id. The requester never sends a raw
    clinic id, so they cannot target or probe an arbitrary clinic."""
    return db.execute(
        text("SELECT id FROM clinics WHERE slug = :slug AND archived_at IS NULL AND status = 'active'"),
        {"slug": clinic_slug.strip().casefold()},
    ).scalar_one_or_none()


def store_access_request(db: Session, clinic_id: UUID, *, email: str, display_name: str | None, requested_role: str | None, reason: str | None) -> None:
    """Record a pending access request. Caller must have set tenant context for
    clinic_id. No-ops (enumeration-safe) when the email already belongs to an
    active member, and the partial unique index collapses duplicate pending
    requests for the same email. Grants NO access by itself."""
    normalized = normalize_email(email)
    already_member = db.execute(
        text("SELECT 1 FROM users WHERE clinic_id = :clinic_id AND normalized_email = :email AND status = 'active'"),
        {"clinic_id": clinic_id, "email": normalized},
    ).scalar_one_or_none()
    if already_member is not None:
        return
    db.execute(
        text("""
            INSERT INTO access_requests (clinic_id, normalized_email, display_name, requested_role, reason)
            VALUES (:clinic_id, :email, :display_name, :requested_role, :reason)
            ON CONFLICT (clinic_id, normalized_email) WHERE status = 'pending' DO NOTHING
        """),
        {"clinic_id": clinic_id, "email": normalized, "display_name": display_name,
         "requested_role": requested_role, "reason": reason},
    )


def _load_pending_for_update(db: Session, clinic_id: UUID, request_id: UUID, expected_version: int) -> dict:
    req = db.execute(
        text("SELECT normalized_email, status, version FROM access_requests WHERE clinic_id = :clinic_id AND id = :id FOR UPDATE"),
        {"clinic_id": clinic_id, "id": request_id},
    ).mappings().one_or_none()
    if req is None:
        raise AccessRequestError("NOT_FOUND", "Access request not found.", 404)
    if req["status"] != "pending":
        raise AccessRequestError("CONFLICT", "This request has already been decided.", 409)
    if req["version"] != expected_version:
        raise AccessRequestError("VERSION_CONFLICT", "This request changed since you loaded it.", 409)
    return dict(req)


def approve_access_request(db: Session, clinic_id: UUID, admin_user_id: UUID, request_id: UUID, *, role_name: str, expected_version: int) -> str:
    """Approve a pending request: issue a staff invitation with the admin-chosen
    role and link it to the request. Returns the raw invitation token. Caller
    commits. The role must be a global template (roles WHERE clinic_id IS NULL),
    which is what the invitation-acceptance flow can assign."""
    if db.execute(text("SELECT 1 FROM roles WHERE clinic_id IS NULL AND name = :name"), {"name": role_name}).scalar_one_or_none() is None:
        raise AccessRequestError("INVALID_INPUT", "Unknown role.", 400)
    _load_pending_for_update(db, clinic_id, request_id, expected_version)
    email = db.execute(text("SELECT normalized_email FROM access_requests WHERE clinic_id = :clinic_id AND id = :id"),
                       {"clinic_id": clinic_id, "id": request_id}).scalar_one()
    token = create_staff_invitation(db, clinic_id, admin_user_id, email, role_name=role_name)
    invitation_id = db.execute(text("SELECT id FROM staff_invitations WHERE token_hash = :token_hash"),
                               {"token_hash": hash_token(token)}).scalar_one()
    db.execute(
        text("""
            UPDATE access_requests
            SET status = 'approved', decided_by_user_id = :uid, decided_at = now(),
                invitation_id = :invitation_id, updated_at = now(), version = version + 1
            WHERE clinic_id = :clinic_id AND id = :id
        """),
        {"uid": admin_user_id, "invitation_id": invitation_id, "clinic_id": clinic_id, "id": request_id},
    )
    return token


def reject_access_request(db: Session, clinic_id: UUID, admin_user_id: UUID, request_id: UUID, *, expected_version: int, note: str | None) -> None:
    """Reject a pending request. Caller commits. The optional note is internal
    (never surfaced to the requester)."""
    _load_pending_for_update(db, clinic_id, request_id, expected_version)
    db.execute(
        text("""
            UPDATE access_requests
            SET status = 'rejected', decided_by_user_id = :uid, decided_at = now(),
                decision_note = :note, updated_at = now(), version = version + 1
            WHERE clinic_id = :clinic_id AND id = :id
        """),
        {"uid": admin_user_id, "note": note, "clinic_id": clinic_id, "id": request_id},
    )

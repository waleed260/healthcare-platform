"""Shared, safe patient identity resolution.

One resolver for every caller that must turn a (name, email, phone) tuple into a patient:
internal appointment booking, public booking, and lead conversion. It replaces the two
divergent ad-hoc lookups that silently attached to an arbitrary patient on a conflicting
email/phone match and did not exclude archived or merged-away records.

Contract:
- Only ACTIVE, non-duplicate patients are candidates (``archived_at IS NULL AND duplicate_of IS NULL``).
- Exactly one match -> use it.
- More than one match (e.g. email -> patient A, phone -> patient B):
    * interactive caller (staff present) -> raise ``DuplicatePatientReview`` so a human chooses;
    * non-interactive caller (public website) -> create a NEW patient, never silently pick one.
- No match -> create a new patient.

Callers pass already-normalised email/phone and the patient_number to mint on create, so this
module stays free of HTTP and normalisation concerns. Never merges records (ADR 0001 soft gate).
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


class DuplicatePatientReview(Exception):
    """Raised when email/phone match more than one active patient and a human must choose.

    ``candidates`` is the ordered list of candidate patient ids (oldest first); route layers
    map this to a 409 ``DUPLICATE_REVIEW_REQUIRED`` response.
    """

    def __init__(self, candidates: list[UUID]) -> None:
        self.candidates = candidates
        super().__init__("duplicate patient review required")


def find_active_patient_candidates(db: Session, clinic_id, email: str | None, phone: str | None) -> list[UUID]:
    """Active, non-duplicate patients whose email or phone matches. At most two are needed."""
    if email is None and phone is None:
        return []
    return list(db.execute(text("""
        SELECT id FROM patients
        WHERE clinic_id = :clinic_id AND archived_at IS NULL AND duplicate_of IS NULL
          AND ((:email IS NOT NULL AND normalized_email = :email)
               OR (:phone IS NOT NULL AND normalized_phone = :phone))
        ORDER BY created_at
        LIMIT 2
    """), {"clinic_id": clinic_id, "email": email, "phone": phone}).scalars().all())


def resolve_patient(
    db: Session,
    clinic_id,
    *,
    full_name: str,
    email: str | None,
    phone: str | None,
    patient_number: str,
    date_of_birth=None,
    interactive: bool,
) -> UUID:
    """Return the single matching active patient, or create one. See module docstring."""
    candidates = find_active_patient_candidates(db, clinic_id, email, phone)
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1 and interactive:
        raise DuplicatePatientReview(candidates)
    # No match, or a non-interactive conflict: create rather than guess.
    return db.execute(text("""
        INSERT INTO patients (clinic_id, patient_number, full_name, normalized_email, normalized_phone, date_of_birth)
        VALUES (:clinic_id, :patient_number, :full_name, :email, :phone, :dob)
        RETURNING id
    """), {
        "clinic_id": clinic_id, "patient_number": patient_number, "full_name": full_name,
        "email": email, "phone": phone, "dob": date_of_birth,
    }).scalar_one()

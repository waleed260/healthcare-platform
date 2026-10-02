"""Central, transactional patient-merge service.

The merge route used to inline a handful of ``UPDATE ... SET patient_id`` calls
and silently omitted most patient-owned domains (documents, media, treatment
plans, packages, prescriptions, clinical forms/tools, and — invisibly to the
earlier review — invoices). After such a partial merge the source patient's
scans, prescriptions, treatment plans, invoices and tool states vanished from
the UI because they still pointed at the archived source row.

This module makes the relationship set explicit and exhaustive. Every table
that is *directly* patient-scoped (has its own ``patient_id`` column) must be
listed here; indirect children follow their parent through the existing foreign
keys and ``ON DELETE CASCADE`` chains, so they are documented but not rewritten:

    treatment_plan_items  -> follows treatment_plans.plan_id
    package_sessions      -> follows patient_packages.patient_package_id
    invoice_lines         -> follows invoices.invoice_id
    payments              -> follows invoices.invoice_id

Adding a new patient-owned table in a future migration should fail a merge test
until it is registered here (see ``test_patient_merge_integration``), which is
the point of keeping the registry in one place.

The whole merge runs in the caller's transaction and is committed once by the
route; any failure rolls the entire merge back, so a patient can never be left
split across the source and target rows.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

# Tables with a direct ``patient_id`` that are simply repointed source -> target.
# ``patient_media.storage_key`` is a random, patient-independent object key, so
# repointing ownership never requires moving the stored object.
_DIRECT_REPOINT = (
    "appointments",
    "follow_up_tasks",
    "patient_notes",
    "consent_records",
    "patient_contacts",
    "patient_documents",
    "patient_media",
    "treatment_plans",
    "patient_packages",
    "prescriptions",
    "clinical_form_responses",
    "invoices",
    # Compliance history for the data subject — keep it with the surviving patient.
    # (Both the GLM and the independent review missed these two.)
    "privacy_requests",
    "export_jobs",
)

# Many-to-many membership tables: move rows that do not already exist on the
# target, then drop the source rows. Dedupe is on the table's natural unique key.
_DEDUPE_MEMBERSHIP = (
    ("patient_care_team", "clinic_id, patient_id, doctor_id, assigned_by_user_id", "clinic_id, :target, doctor_id, assigned_by_user_id"),
    ("patient_tags", "clinic_id, patient_id, tag_id", "clinic_id, :target, tag_id"),
)


def merge_patients(db: Session, *, clinic_id: UUID, actor_user_id: UUID, source_id: UUID, target_id: UUID, reason: str | None) -> dict[str, int]:
    """Move every patient-owned relationship from ``source_id`` to ``target_id``.

    Returns a per-table count of rows moved for the audit trail. Callers are
    responsible for validating source/target (different, same clinic, locked
    ``FOR UPDATE``) and for committing the surrounding transaction.
    """
    params = {"clinic_id": clinic_id, "source": source_id, "target": target_id}
    counts: dict[str, int] = {}

    for table in _DIRECT_REPOINT:
        result = db.execute(
            text(f"UPDATE {table} SET patient_id = :target WHERE clinic_id = :clinic_id AND patient_id = :source"),
            params,
        )
        counts[table] = result.rowcount or 0

    for table, insert_columns, select_expr in _DEDUPE_MEMBERSHIP:
        db.execute(
            text(f"INSERT INTO {table} ({insert_columns}) SELECT {select_expr} FROM {table} WHERE clinic_id = :clinic_id AND patient_id = :source ON CONFLICT DO NOTHING"),
            params,
        )
        result = db.execute(
            text(f"DELETE FROM {table} WHERE clinic_id = :clinic_id AND patient_id = :source"),
            params,
        )
        counts[table] = result.rowcount or 0

    # clinical_tool_states has UNIQUE (clinic_id, patient_id, tool_key); a blind
    # repoint would collide whenever the target already holds that tool. Rule:
    # the target's existing tool state wins, so drop the source's conflicting
    # rows first, then repoint the remainder.
    db.execute(
        text("""
            DELETE FROM clinical_tool_states src
            WHERE src.clinic_id = :clinic_id AND src.patient_id = :source
              AND EXISTS (
                SELECT 1 FROM clinical_tool_states tgt
                WHERE tgt.clinic_id = :clinic_id AND tgt.patient_id = :target
                  AND tgt.tool_key = src.tool_key
              )
        """),
        params,
    )
    result = db.execute(
        text("UPDATE clinical_tool_states SET patient_id = :target WHERE clinic_id = :clinic_id AND patient_id = :source"),
        params,
    )
    counts["clinical_tool_states"] = result.rowcount or 0

    # Converted leads keep their own history but must point at the surviving patient.
    result = db.execute(
        text("UPDATE leads SET converted_to_patient_id = :target WHERE clinic_id = :clinic_id AND converted_to_patient_id = :source"),
        params,
    )
    counts["leads.converted_to_patient_id"] = result.rowcount or 0

    # Tombstone the source; never hard-delete (the merge event is the audit record).
    db.execute(
        text("UPDATE patients SET duplicate_of = :target, status = 'merged', archived_at = now(), version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :source"),
        params,
    )
    db.execute(
        text("INSERT INTO patient_merge_events (clinic_id, source_patient_id, target_patient_id, actor_user_id, reason) VALUES (:clinic_id, :source, :target, :actor, :reason)"),
        {"clinic_id": clinic_id, "source": source_id, "target": target_id, "actor": actor_user_id, "reason": reason},
    )
    return counts

# ADR 0001 — Patient duplicate detection is a soft gate, by design

- **Status:** Accepted (2026-10-03)
- **Area:** `crm` — patient create / convert

## Context

When a patient is created (`patient_create`) or a lead is converted
(`lead_convert`), the API runs a best-effort pre-check for an existing patient
with the same normalized email or phone. There is **no** unique index on
normalized email/phone, so the check is advisory: two concurrent creates can
both pass it and produce two records with the same contact details.

## Decision

Keep the gate soft. A hard unique constraint on email/phone would be wrong for a
clinic: family members (children, spouses, dependents) legitimately share a
phone number or email address, and a unique index would block those real
patients from being registered.

## Consequences

- Duplicates remain *possible*, and that is accepted.
- The compensating controls are:
  - **`duplicate_candidates`** — a ranked list of likely matches surfaced to
    staff *before* they create a patient, so most duplicates are caught at entry.
  - **The patient-merge workflow** (`crm/merge.py`) — repoints all patient-scoped
    tables onto a surviving record, tombstones the source, and audits the merge,
    so any duplicates that do slip through can be reconciled without data loss.
- Because the gate is not a constraint, callers must not rely on it for
  correctness; it reduces, but does not eliminate, duplicate creation.

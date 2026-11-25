# ADR 0002 — Lead lifecycle is driven by real appointment events, not manual labels

- **Status:** Proposed (2026-11-25)
- **Area:** `blueprint_core` (leads) ↔ `appointments` ↔ `crm` (patient identity)
- **Supersedes nothing. Companion to:** ADR 0001 (soft-duplicate gate), `docs/LEADS_IMPLEMENTATION_PLAN.md`

## Context

The lead pipeline exposes two stages that are supposed to represent real clinic
events — `appointment_booked` and `visited` — but neither is connected to the
appointment subsystem:

- `leads.appointment_id` exists (`migrations/versions/0046_blueprint_core_foundations.py:93,104`)
  but **no code writes it**; it is read-only (`blueprint_core/routes.py:144,167` and the
  scope sub-query `:47-51`).
- `apps/api/app/modules/appointments/routes.py` never references leads. There is no
  `appointments.lead_id`. Booking from a lead (`add-appointment-drawer.tsx`) sends no lead id.
- Both stages are reachable only by a manual dropdown, and moving a lead to `visited`
  **silently creates/links a patient and marks the lead converted-in-effect**
  (`blueprint_core/routes.py:244-252,262-263`), then freezes it (`:202-205,:420`).

This conflates four distinct business facts — *booking*, *attendance*, *patient
association*, and *formal conversion* — into dropdown clicks, so the pipeline numbers do
not reflect reality.

Separately, internal and public booking resolve a patient with
`(email=:e OR phone=:p) ORDER BY created_at LIMIT 1` and **no** archived/duplicate filter
(`appointments/routes.py:497,887`), which can silently attach an appointment to the wrong,
archived, or merged patient.

## Decision

1. **The lead→appointment relationship is one-to-many via a new `appointments.lead_id`**
   (composite FK to `leads(clinic_id, id)`, `ON DELETE SET NULL`). It is the single source
   of truth. The dead scalar `leads.appointment_id` is redefined as derived and dropped in a
   later migration once readers use `appointments.lead_id`.
2. **Stages are driven by domain events, not manual input:**
   - `appointment_booked` ← the booking service creates an appointment linked to the lead,
     in the same transaction, guarded `WHERE status IN ('new','contacted','qualified')`.
   - `visited` ← the linked appointment's authoritative transition to `arrived`
     (`appointments/routes.py:~349`), exactly once, idempotent. **Booking is never a visit.**
   - `converted` ← an explicit `POST /leads/{id}/convert` requiring a new `lead.convert`
     permission and a valid patient. **Never an automatic side-effect.**
   The manual `PATCH` path refuses the event-only targets (`appointment_booked`, `visited`,
   `converted`).
3. **Patient association and formal conversion are separate.** Association is *derived* from
   the lead's most-recent linked appointment's `patient_id`; it does not set
   `converted_to_patient_id` and does not make the lead terminal. Only explicit conversion is
   terminal.
4. **One shared, safe patient resolver** (`crm/identity.resolve_patient`) replaces the two
   divergent resolvers: it filters `archived_at IS NULL AND duplicate_of IS NULL`, returns a
   single unambiguous match, raises `DUPLICATE_REVIEW_REQUIRED` on conflicting matches for
   interactive callers, and (for the public, non-interactive path) creates a new patient plus
   a reconcile marker rather than guessing. It never silently merges.
5. **Cancellation / no-show never lose the lead.** If no other active appointment remains,
   the lead returns `appointment_booked → qualified` and a follow-up task is created.

## Consequences

- The 7-status vocabulary is unchanged, so `ck_leads_status`, the operations funnel
  `GROUP BY l.status` (`operations/routes.py:227`), and the frontend are undisturbed.
- `converted_to_patient_id` keeps meaning "formally converted", so the funnel conversion
  metric (`:286-287`) stays correct, and merge/reconcile wiring
  (`crm/merge.py:128-131`, `reconcile_merges.py:36`) is unchanged.
- Appointments with `lead_id IS NULL` behave exactly as today; every new branch is guarded on
  `lead_id IS NOT NULL`, so non-lead booking/patient flows do not regress.
- New `lead_follow_ups` and `lead_stage_history` tables must enforce `ENABLE`+`FORCE` RLS or
  the self-maintaining forced-RLS test fails the build.
- The only destructive migration (dropping `leads.appointment_id`) is deferred behind a
  reader-migration compatibility window.

## Alternatives considered

- **Keep a hand-maintained `leads.appointment_id` pointer alongside `appointments.lead_id`** —
  rejected: two sources of truth that drift (mission explicitly warns against this).
- **Overload the existing patient `follow_up_tasks` table with a nullable `lead_id`** —
  rejected: forces a migration on a core, funnel-wired table and pollutes patient-recall
  counts; a dedicated `lead_follow_ups` table is smaller blast radius.
- **A hard unique index on normalized email/phone to stop duplicates** — rejected by ADR 0001
  (families legitimately share contacts); the soft gate + `duplicate_candidates` remains.

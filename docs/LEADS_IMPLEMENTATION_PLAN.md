# care/fully — Leads Management Implementation Plan

- **Status:** Blueprint (planning only — no code, migrations, or commits produced by this document)
- **Author basis:** Audit of the live repository on branch `fix/contract-drift-regen`, 2026-11-25
- **Scope:** The Leads domain and its connections to Appointments, Patient identity, Follow-ups, RBAC, tenant isolation, and audit.
- **Companion ADR:** `docs/blueprint/adr/0002-lead-lifecycle-and-appointment-linkage.md`

> **How to read this document.** Statements tagged **FACT** are things verified in the current
> code, each with a `file:line` citation. Statements tagged **RECOMMENDATION** are proposed
> changes. Nothing here has been implemented. A senior engineer should be able to build the
> module from Sections 5–19 without re-guessing the business rules.

---

## 1. Executive summary

The Leads module today is a **CRUD pipeline with a decorative state machine**. Leads can be
created (manually or from the public website), listed with tenant + specialty + branch scope,
moved between stages with a dropdown, given an immutable activity timeline, and "converted" to a
patient. Underneath, the two stages that are supposed to represent *real clinic events* —
`appointment_booked` and `visited` — are not connected to anything:

- **FACT:** `leads.appointment_id` exists (`apps/api/migrations/versions/0046_blueprint_core_foundations.py:93,104`) but **no code path ever writes it**. It is only ever SELECTed (`apps/api/app/modules/blueprint_core/routes.py:144,167` and the scope sub-query at `:47-51`).
- **FACT:** `apps/api/app/modules/appointments/routes.py` contains **zero references to leads**; neither internal booking (`:447`) nor public booking (`:790`) links or advances a lead. There is no `appointments.lead_id` column.
- **FACT:** The frontend "Book appointment" button (`apps/web/app/(authenticated)/leads/page.tsx`) only pre-fills the patient step of `AddAppointmentDrawer` via `initialPatient`; the booking POST body carries no lead id (`apps/web/app/(authenticated)/_lib/add-appointment-drawer.tsx:188-212`).

So `appointment_booked` and `visited` are reachable **only by a manual dropdown**
(`leads/page.tsx:18-24`) and mean nothing. Worse, moving a lead to `visited` **silently
auto-creates/links a patient and records a `lead.convert` audit** (`blueprint_core/routes.py:244-252,262-263`),
conflating three distinct business events — *attendance*, *patient association*, and *formal
conversion* — into one dropdown click, and then **freezes the lead** (`:202-205,:420`).

This plan keeps the existing 7-status vocabulary and the existing tables (so the operations
funnel, the status `CHECK` constraint, and the frontend are undisturbed) and **re-grounds the
lifecycle on real domain events**:

1. `appointment_booked` ← a real appointment is created and linked to the lead (new `appointments.lead_id`, one-to-many).
2. `visited` ← that appointment's authoritative transition to `arrived` (real attendance), exactly once, idempotent.
3. `converted` ← an explicit, separately-permissioned conversion action with a valid patient; **never** an automatic side-effect.
4. One shared, safe patient identity-resolution service replaces the two divergent resolvers (one of which silently attaches an appointment to an arbitrary patient).
5. A dedicated actionable **`lead_follow_ups`** table (the immutable `lead_activities` log stays immutable), a **`lead_stage_history`** table, and an **acquisition-source / capture-method** split so manual leads are never labelled "website".

The highest-risk area is the appointment↔lead↔patient transaction. The migrations are additive
and backfillable; the only destructive step (dropping the dead `leads.appointment_id` scalar) is
deferred to the final phase behind a compatibility window.

---

## 2. Existing architecture (FACT, with citations)

### 2.1 Lead persistence

| Concern | Where | Notes |
|---|---|---|
| `leads` table | `migrations/versions/0046_blueprint_core_foundations.py:80-108` | Columns: `full_name, normalized_email, normalized_phone, source, campaign, specialty_id, requested_service_id, assigned_to_user_id, status, notes, appointment_id, converted_to_patient_id, lost_reason, version, archived_at`. `CHECK ck_leads_status IN (new, contacted, qualified, appointment_booked, visited, converted, lost)`. Composite FKs to `clinic_specialties`, `services`, `users`, `appointments (ON DELETE SET NULL)`, `patients (ON DELETE RESTRICT)`. `UNIQUE (clinic_id, id)` so children can hold composite FKs. |
| RLS | `0046:...` RLS helper (`ENABLE`+`FORCE`+tenant policy) at `:13-17`; guarded by `tests/..._every_clinic_owned_table_has_forced_rls` | leads and lead_activities are tenant-forced. |
| `branch_id` | `0093_leads_branch_id.py` | Nullable; NULL = "unassigned", visible only to users without branch scopes. Scope SQL falls back to the linked appointment's branch. |
| `intake_key` | `0052_public_lead_intake.py` | Idempotency for public intake; partial unique `(clinic_id, intake_key)`. |
| `lead_activities` | `0057_lead_activities.py` | **Immutable**: runtime granted `SELECT, INSERT` only (`:50`). Kinds: `call, note, message, follow_up`; `follow_up` requires `due_at` (`CHECK :27-28`). No completion lifecycle. |

### 2.2 Lead API (`apps/api/app/modules/blueprint_core/routes.py`)

| Endpoint | Line | Permission | Behaviour |
|---|---|---|---|
| `GET /api/v1/leads` | `:132` | `lead.read` | Cursor-paginated, tenant + `_LEAD_SCOPE_SQL` (specialty+branch) filtered. |
| `GET /api/v1/leads/{id}` | `:160` | `lead.read` | `_require_lead` scope-gate + detail. |
| `POST /api/v1/leads` | `:178` | `lead.manage` | Insert. **No scope validation** (see D7). |
| `PATCH /api/v1/leads/{id}` | `:191` | `lead.manage` | Version-checked; validates lead transition; specialty/branch scope checks (`:211-236`); **auto-converts on `visited`** (`:244-252`). |
| `POST /api/v1/leads/{id}/activities` | `:351` | `lead.manage` | Append immutable activity. |
| `GET …/activities` | `:310` | `lead.read` | Paginated timeline. |
| `POST /api/v1/leads/{id}/convert` | `:380` | `lead.manage` | Resolve/create patient, set `converted`. Idempotent via `converted_to_patient_id IS NULL` guard. |
| `POST …/archive`, `…/unarchive` | `:413,:428` | `lead.manage` | Soft archive; blocked if converted. |

- **Transition table:** `apps/api/app/modules/blueprint_core/lead_state.py:6-14` — `ALLOWED_TRANSITIONS`. `converted` is terminal; `lost → {new, contacted}` (reopen).
- **Object scope:** `_LEAD_SCOPE_SQL` (`routes.py:33-54`) — a lead is visible if the user has no specialty scopes OR the lead's specialty is in scope, AND (no branch scopes OR lead's branch — falling back to the linked appointment's branch — is in scope).
- **Patient resolver (lead side):** `_resolve_or_create_patient` (`:287-307`) — matches active, non-duplicate patients on email **or** phone, `LIMIT 2`; `>1` ⇒ `DUPLICATE_REVIEW_REQUIRED` (409); else returns the one or creates a `PENDING-…` patient.

### 2.3 Appointment lifecycle (`apps/api/app/modules/appointments/`)

- **States:** `state.py:6-16` — `requested→{confirmed,cancelled}`, `confirmed→{arrived,rescheduled,cancelled,no_show}`, `arrived→{waiting,cancelled}`, `waiting→{in_consultation,cancelled,confirmed}`, `in_consultation→{completed}`; `completed/rescheduled/cancelled/no_show` terminal.
- **Status transition endpoint:** `routes.py:~320-353` — permission picked by target (`appointment.approve|cancel|check_in|manage`, `:330`); `to_status=='arrived'` ⇒ `appointment.check_in`. Writes `appointment_history` (`:352`) and audits `appointment.{to_status}` (`:353`). **This is the authoritative attendance signal.**
- **Internal booking:** `create_internal_booking` (`:447-525`). Patient resolution at `:489-501`.
- **Public booking:** `create_public_booking` (`:790-918`). Patient resolution at `:885-889`.
- **Reschedule:** `:399-438` — creates a **new** appointment row with `supersedes_appointment_id`, inserts two `appointment_history` rows. (A natural fit for carrying the lead link onto the replacement.)
- **Idempotency:** `Idempotency-Key` header required; `uq_appointments_idempotency` + `_replay_idempotent_booking` (`:639`).

### 2.4 Patient identity & merge

- **Soft-duplicate gate** is a deliberate design: `docs/blueprint/adr/0001-soft-duplicate-gate.md`. No unique index on email/phone (families share contacts). Compensating control: `duplicate_candidates` endpoint (`crm/routes.py:263`) + `reconcile_merges.py`.
- **Merge** repoints `leads.converted_to_patient_id` (`crm/merge.py:128-131`) and all `patient_id` tables; `scripts/reconcile_merges.py:36` includes `leads.converted_to_patient_id`.

### 2.5 Downstream consumers of lead data (must not regress)

- **Operations funnel** `apps/api/app/modules/operations/routes.py`: demand breakdown `GROUP BY l.status` (`:227`), conversion metric counts `converted_to_patient_id IS NOT NULL` (`:286-287`), plus lead reads at `:462,:481`.
- **Frontend:** `leads/page.tsx`, `leads/[leadId]/page.tsx` (reads `converted_to_patient_id` at `:227-228`), `_lib/add-appointment-drawer.tsx`.
- **Existing follow-up table (patient-bound, do not overload):** `follow_up_tasks` (`migrations/versions/0007_operations_queue.py`) — `patient_id NOT NULL`, statuses `due|contacted|booked`, wired into the funnel (`operations/routes.py:148,210-216`). It cannot host lead follow-ups without a risky core-table change.
- **Tests:** `apps/api/tests/test_lead_activities.py`, `test_lead_activities_integration.py`, `test_lead_pagination_integration.py`, `test_lead_scope_integration.py`, `test_blueprint_core_schemas.py`, `test_patient_merge_integration.py`; `apps/web/tests/lead-timeline.spec.ts`.

---

## 3. Verified current defects

Each is reproduced from code; see Section 19 for the consolidated classification table.

- **D1 — The lead↔appointment relationship is non-functional.** `leads.appointment_id` is never written (no writer anywhere); `appointments` code never references leads; the booking drawer sends no lead id. Therefore `appointment_booked` represents no real appointment, and the `_LEAD_SCOPE_SQL` branch fallback (`routes.py:47-51`) is dead for every lead. *Evidence:* `0046:93,104`; `grep` shows only SELECTs of `appointment_id` in `blueprint_core/routes.py:144,167`; no `appointments.lead_id`; `add-appointment-drawer.tsx:188-212`.
- **D2 — `visited` silently performs a conversion.** `PATCH …/{id}` with `status='visited'` auto-creates/links a patient and writes a `lead.convert` audit with `auto:True`. *Evidence:* `blueprint_core/routes.py:244-252,262-263`. Violates "patient association ≠ formal conversion" and "booking ≠ attendance".
- **D3 — Patient association prematurely freezes the lead.** Once `converted_to_patient_id` is non-null, any status change is rejected (`LEAD_CONVERTED`, `:202-205`) and archive is blocked (`:420`). Combined with D2, a `visited` lead is permanently stuck and its `status` ("visited") disagrees with its converted-patient link — state drift. *Evidence:* `:202-205,:420`.
- **D4 — Booking silently attaches to an arbitrary / unsafe patient.** Internal (`:497`) and public (`:887`) booking resolve a patient with `(email=:e OR phone=:p) ORDER BY created_at LIMIT 1`, **without** `archived_at IS NULL` / `duplicate_of IS NULL`. If email→patient A and phone→patient B, it silently picks the older; it can also attach to an archived or merged patient. Diverges from the safer lead-side resolver (`:287-307`). *Evidence:* `appointments/routes.py:497,887` vs `blueprint_core/routes.py:293-300`.
- **D5 — No actionable follow-up model for leads.** `lead_activities` is INSERT+SELECT only (`0057:50`); its `follow_up` kind has a `due_at` but no `status/completed_at/completed_by/cancel`. "Overdue" is only client-derived. The existing `follow_up_tasks` table is patient-bound (`patient_id NOT NULL`, `0007`). *Evidence:* `0057_lead_activities.py:50`; `0007_operations_queue.py`.
- **D6 — Acquisition source and capture method are conflated; manual leads can be mislabelled "website".** Single free-text `source` column; public intake hardcodes `source='website'` (`websites/routes.py:62`, `website_content/routes.py:142`), and the manual form offers "website" as a `source` option (`leads/page.tsx:25,141`). No `capture_method`. *Evidence:* `0046:86`; the two public inserts; `leads/page.tsx:25`.
- **D7 — `lead_create` has no object-scope validation ⇒ self-invisible leads.** Unlike `lead_update` (`:211-236`), `lead_create` (`:178-188`) does not check that `specialty_id`/`branch_id` are in the creator's scope. A branch-scoped user who sets an out-of-scope branch creates a lead they immediately cannot see (filtered by `_LEAD_SCOPE_SQL`). *Evidence:* `:178-188` vs `:211-236` + `:33-54`.
- **D8 — No queryable lead stage history; reopen keeps `lost_reason`; no dedicated conversion permission.** Stage changes are only generic `record_event` rows (no per-lead `from/to/actor/reason` history like `appointment_history`). Reopen (`PATCH lost→new`) does not clear `lost_reason`. Convert uses `lead.manage`; the registry has only `lead.read`, `lead.manage` (`authorization/permissions.py:52-53`). *Evidence:* no `lead_stage_history` migration exists; `permissions.py:52-53`; reopen path `leads/page.tsx:133`.

---

## 4. Target product behaviour

1. **Manual staff entry is the primary intake.** The public website and custom-form intakes keep working unchanged and are correctly labelled by `capture_method`.
2. **Every stage is a real business event.** Booking requires a real linked appointment; "visited" means the patient actually arrived; "converted" is a deliberate, separately-authorised act with a valid patient.
3. **Patient association, attendance, and conversion are three separate facts.** None of them silently triggers another, and none except explicit conversion makes the lead terminal.
4. **A lead can accumulate many appointments over its life** (original, reschedule replacement, re-booking after a no-show) and shows them all.
5. **One safe patient-identity resolver** everywhere; conflicting matches are surfaced for a human decision, never silently merged, and never attach to an archived/merged record.
6. **Actionable follow-up tasks** with pending/completed/cancelled + overdue, on top of the immutable activity timeline.
7. **Scope-safe by construction:** a user can never create a lead they cannot then see.
8. Tenant isolation, RBAC, audit, and the soft-duplicate design (ADR 0001) are preserved.

---

## 5. Final lead lifecycle

Statuses are **unchanged** (`new, contacted, qualified, appointment_booked, visited, converted, lost`) so the `ck_leads_status` constraint, the funnel `GROUP BY l.status`, and the frontend keep working. What changes is **what drives each stage** and **who may trigger it**.

| Stage | Meaning | Entered by | Trigger event | Who |
|---|---|---|---|---|
| `new` | Fresh enquiry, not yet worked | Create (manual/public), or reopen from `lost` | `POST /leads`, public intake, or manual reopen | `lead.manage` / public |
| `contacted` | A contact attempt was logged | **Manual** | `PATCH status` | `lead.manage` |
| `qualified` | Interest + requested service/specialty confirmed | **Manual** (or event return from `appointment_booked`) | `PATCH status`, or all linked appts cancelled/no_show | `lead.manage` / system |
| `appointment_booked` | A real appointment is linked | **Event** | Booking service creates an appointment with `lead_id` | `appointment.create` (via booking) |
| `visited` | The patient actually attended | **Event** | Linked appointment → `arrived` | `appointment.check_in` (via transition) |
| `converted` | Formal conversion to a patient record | **Event via explicit action** | `POST /leads/{id}/convert` with a valid patient | `lead.convert` |
| `lost` | Enquiry abandoned, with reason | **Manual** | `PATCH status=lost` (+ `lost_reason`) | `lead.manage` |

Required fields per stage:
- `lost` requires `lost_reason` (already enforced, `schemas.py:62-63`; keep).
- `converted` requires a resolvable/selected patient (Section 7).
- `appointment_booked`/`visited` require the backing appointment/attendance to exist (enforced by being event-only — the manual API refuses these targets).

After cancellation/no-show (Section 5 of the mission, Flows G/H): the lead is **not** marked lost and **not** marked visited. If no other active appointment remains, the lead returns `appointment_booked → qualified` and a follow-up task is created.

Reopening a `lost` lead (Flow J): `lost → {new, contacted}`, authorised by `lead.manage`, **clears `lost_reason`** (fixes D8) and records stage history.

Protecting converted leads: `converted` is terminal (no outbound transitions). A patient association alone (a linked appointment that has a patient) does **not** make the lead terminal (fixes D3).

---

## 6. State transition matrix

**RECOMMENDATION** — replace `lead_state.ALLOWED_TRANSITIONS` with the following, and annotate each transition as Manual (allowed through `PATCH status`) or Event (backend-only; the manual API rejects it with `INVALID_TRANSITION`).

```
new               → contacted (M), qualified (M), appointment_booked (E), lost (M), converted (E)
contacted         → qualified (M), new (M), appointment_booked (E), lost (M), converted (E)
qualified         → contacted (M), appointment_booked (E), lost (M), converted (E)
appointment_booked→ visited (E), qualified (E: all appts cancelled/no_show), lost (M), converted (E)
visited           → converted (E), lost (M)
converted         → ∅            (terminal)
lost              → new (M), contacted (M)   (reopen; clears lost_reason)
```

Enforcement rules:
- **Event-only targets** (`appointment_booked`, `visited`, `converted`) are **not** accepted through `PATCH /leads/{id}` (the manual path). `LeadUpdate.status` already excludes `converted` (`schemas.py:42`); **RECOMMENDATION:** also exclude `appointment_booked` and `visited` from the manual `status` literal, so staff cannot fake a booking or a visit. These stages are set only by the booking service, the appointment-transition hook, and the convert endpoint respectively.
- Every transition (manual or event) writes a `lead_stage_history` row and an audit event.
- Direct SQL `UPDATE leads SET status=…` must carry a `WHERE status IN (…)` guard matching the matrix (same rule the repo applies to appointments, per `CLAUDE.md`).

---

## 7. Appointment-to-lead and patient-identity workflow (highest priority)

### 7.1 The link: `appointments.lead_id` (one-to-many)

**RECOMMENDATION.** Add `appointments.lead_id uuid NULL` with composite FK `(clinic_id, lead_id) → leads(clinic_id, id) ON DELETE SET NULL` and index `(clinic_id, lead_id)`. This makes "a lead has many appointments" the single source of truth and fits the existing reschedule model (the replacement row simply inherits `lead_id`, so Flow I shows both records).

- `leads.appointment_id` (the dead scalar) is **redefined as derived** — the lead's most-recent linked appointment — and readers (`_LEAD_SCOPE_SQL:47-51`, detail SELECT) switch to `appointments.lead_id`. The scalar column is **dropped in the final phase** after readers migrate (Section 15), avoiding a duplicated source of truth (mission §5).
- **Rejected alternative:** keep a hand-maintained `leads.appointment_id` pointer in addition to `appointments.lead_id` — two sources of truth that can drift; explicitly warned against by the mission.

### 7.2 Shared patient identity resolution

**RECOMMENDATION.** Extract one resolver (e.g. `app/modules/crm/identity.py: resolve_patient(...)`), used by internal booking, public booking, lead convert, and any lead→patient association. Outcomes:

| Situation | Behaviour |
|---|---|
| No active, non-duplicate match | Create a patient (full for convert; `PENDING-…` for booking-time creation, matching the current lead-side convention `blueprint_core/routes.py:305`). |
| Exactly one unambiguous match | Use it. |
| Multiple candidates, or email→A and phone→B (different active patients) | **Interactive paths** (internal booking, convert): raise `DUPLICATE_REVIEW_REQUIRED` (409) with the candidate list; UI resolves (Flow L). **Public path** (no human to ask): do **not** silently attach — create a new patient and enqueue a duplicate-review (reconcile) marker, so the booking never fails but never guesses wrong. |
| Explicit `patient_id` supplied | Validate it is active + non-duplicate in-tenant (as convert already does, `:395`), then use it. |

All candidate queries **must** filter `archived_at IS NULL AND duplicate_of IS NULL` (fixes D4). This replaces the unsafe `LIMIT 1` resolvers at `appointments/routes.py:497,887`.

### 7.3 Association vs conversion (kept separate)

- **Association** = the patient on the lead's most-recent linked appointment (derived from `appointments.lead_id` + `appointments.patient_id`). It is **not** stored on the lead and is **not** `converted_to_patient_id`. This keeps the funnel conversion metric (`operations/routes.py:286-287`) meaning *conversions only*.
- **Conversion** = `POST /leads/{id}/convert` sets `converted_to_patient_id` + `status='converted'` (terminal), requires `lead.convert`, and uses the derived associated patient by default (or an explicit `patient_id`). Idempotent via the existing `converted_to_patient_id IS NULL` WHERE guard (`:405`) + `FOR UPDATE` (`:384`).

### 7.4 Transactional consistency (one booking transaction)

When an appointment is booked from a lead, inside one transaction:
1. Resolve/create patient (7.2).
2. Insert the appointment with `lead_id` + `patient_id` (idempotent by `Idempotency-Key`).
3. `UPDATE leads SET status='appointment_booked'` **guarded** `WHERE status IN ('new','contacted','qualified')` (so a converted/lost/already-booked lead is untouched — no illegal regressions).
4. Insert `lead_stage_history` + audit.
A failed appointment insert rolls back the lead change (no false "booked"). An idempotent replay returns the existing appointment and performs no second stage event.

### 7.5 Attendance → visited (exactly once)

Hook the appointment status-transition handler (`appointments/routes.py:~349`): when `to_status='arrived'` and the appointment has a `lead_id`, `UPDATE leads SET status='visited' WHERE id=:lead_id AND status='appointment_booked'` (idempotent: a second arrival event, or a lead already past `appointment_booked`, is a no-op), + stage history + audit. Booking never sets `visited`; only real arrival does.

### 7.6 Cancellation / no-show / reschedule

- **Cancel/no_show** (`appointments` transition to `cancelled`/`no_show`): if the lead has **no other active appointment** (`status NOT IN (cancelled, no_show, rescheduled, completed)`), `UPDATE leads SET status='qualified' WHERE id=:lead_id AND status='appointment_booked'`; create a `lead_follow_ups` task ("reschedule — <reason>"). Never auto-`lost`, never `visited`.
- **Reschedule** (`:399-438`): the replacement appointment inherits `lead_id`; the lead stays `appointment_booked`; both appointment rows appear in the lead's appointment history.

Existing non-lead appointment flows (appointments with `lead_id IS NULL`) are completely unaffected — every new branch is guarded on `lead_id IS NOT NULL`.

---

## 8. Follow-up and activity model

- **Keep `lead_activities` immutable** (`0057`) — do not add UPDATE/DELETE grants. It remains the append-only timeline.
- **RECOMMENDATION — new `lead_follow_ups` table** (dedicated; do **not** overload the patient-bound `follow_up_tasks`):

```
lead_follow_ups(
  id uuid pk, clinic_id uuid not null,
  lead_id uuid not null,                         -- composite FK (clinic_id, lead_id) → leads
  assigned_to_user_id uuid null,                 -- composite FK → users
  description text not null,
  due_at timestamptz not null,
  status text not null default 'pending'         -- CHECK in ('pending','completed','cancelled')
  completed_at timestamptz null,
  completed_by_user_id uuid null,                -- composite FK → users
  created_by_user_id uuid not null,              -- composite FK → users
  created_at, updated_at timestamptz not null default now(),
  UNIQUE (clinic_id, id)
)  -- ENABLE+FORCE RLS, tenant policy, GRANT SELECT,INSERT,UPDATE to healthcare_runtime
   -- index (clinic_id, lead_id, due_at), partial index (clinic_id, due_at) WHERE status='pending'
```
`overdue` is **derived**: `status='pending' AND due_at < now()`. Creating / completing / cancelling a follow-up also appends a `lead_activities` row (kind `follow_up`), so the immutable timeline still captures the event.

- **Rejected alternative:** extend `follow_up_tasks` with a nullable `lead_id` and relax `patient_id` to nullable. Rejected: it forces a migration on a core table, a `CHECK (patient_id IS NOT NULL OR lead_id IS NOT NULL)`, and pollutes every patient-recall funnel count (`operations/routes.py:148,210-216`) unless each query adds `lead_id IS NULL`. Larger blast radius and more code than a small dedicated table.

**Timeline events** (written to `lead_activities` and/or surfaced from `lead_stage_history`): call, note, manually-logged message, follow-up created/completed/cancelled, assignment change, stage change, appointment booked/cancelled/rescheduled, visit, patient association, formal conversion, lost/reopened.

**Messaging honesty (mission §8):** a "message" activity is a *manually logged* record of a message the staffer sent through their own channel. The system must not claim it was sent via WhatsApp/Meta/etc. Reminders use only the existing worker infrastructure (`apps/api/app/worker_loop`, `process_once`); no new external provider.

---

## 9. End-to-end flows

Each flow: **UI action → endpoint → validation → DB change → audit → failure → idempotency → tenant/RBAC**. Endpoints marked *(new)* / *(modified)* / *(reuse)* map to Section 11.

### Flow A — Manual new lead
UI: Leads → New Lead → submit. → `POST /api/v1/leads` *(modified: add scope validation, `capture_method`)*. Validation: `LeadCreate` (phone ≥7 digits), **specialty/branch in creator scope** (fixes D7), FK tenancy. DB: insert `leads` (`capture_method='manual_staff_entry'`). Audit: `lead.create`. Failure: `INVALID_INPUT` (bad phone), `FORBIDDEN` (out-of-scope specialty/branch). Idempotency: none required (manual). RBAC: `lead.manage`; tenant via `set_tenant_context`.

### Flow B — Contacting a prospect
UI: open lead → log call/note → optional stage move to `contacted`. → `POST …/activities` + `PATCH …` *(reuse)*. Validation: `LeadActivityCreate`; transition `*→contacted` (manual-allowed). DB: insert `lead_activities`; `leads.status='contacted'` + `lead_stage_history`. Audit: `lead.activity.create`, `lead.update`. RBAC: `lead.manage`.

### Flow C — Qualification
UI: confirm interest + requested service/specialty/branch → `PATCH …` *(reuse)*. Validation: scope checks (`:211-236`), transition to `qualified`. DB: update fields + status; stage history. RBAC: `lead.manage`.

### Flow D — Appointment from lead
UI: Book Appointment → `AddAppointmentDrawer` (lead context retained) → select/create patient, branch/doctor/service/slot → submit. → `POST /api/v1/appointments` *(modified: accept `lead_id`)*. Validation: `InternalBookingRequest` + `lead_id` in-tenant and lead in `{new,contacted,qualified}`; slot availability/conflict as today. DB (one txn, §7.4): resolve patient → insert appointment with `lead_id` → `leads.status='appointment_booked'` (guarded) → `appointment_history` + `lead_stage_history`. Audit: `appointment.create`, `lead.appointment_booked`. Failure: `APPOINTMENT_CONFLICT`, `DUPLICATE_REVIEW_REQUIRED`, `VERSION_CONFLICT`. Idempotency: `Idempotency-Key` (existing). RBAC: `appointment.create` (+ `lead.read` to load context); tenant-scoped.

### Flow E — Patient arrival (visit)
UI: queue/appointment → mark arrived. → `POST /api/v1/appointments/{id}/status` `to_status=arrived` *(modified: lead hook)*. Validation: appointment transition `confirmed→arrived`; `appointment.check_in`. DB: appointment update + history; **if `lead_id`**: `leads.status='visited'` guarded `WHERE status='appointment_booked'` (exactly once) + stage history. Audit: `appointment.arrived`, `lead.visited`. Idempotency: second arrival = no-op on the lead. RBAC: `appointment.check_in`.

### Flow F — Patient conversion
UI: lead detail → Convert → confirm patient (prefilled from the associated/arrived patient). → `POST /api/v1/leads/{id}/convert` *(modified: `lead.convert` permission, decoupled from `visited`)*. Validation: lead not already converted; patient valid (active, non-duplicate); transition `*→converted`. DB: `converted_to_patient_id` + `status='converted'` (idempotent guard) + stage history. Audit: `lead.convert` (no `auto` flag). Failure: `DUPLICATE_REVIEW_REQUIRED`, `LEAD_CONVERTED` (already), `NOT_FOUND`. RBAC: `lead.convert`.

### Flow G — Cancellation
Trigger: appointment → `cancelled`. → appointment transition handler *(modified)*. DB: if no other active appointment for the lead, `appointment_booked→qualified` (guarded) + stage history; create `lead_follow_ups` ("reschedule"). Never `lost`. Audit: `appointment.cancelled`, `lead.update`. Idempotent.

### Flow H — No-show
Trigger: appointment → `no_show`. Same as G (return to `qualified` if no active appt remains, create follow-up). Lead never counted as visited. Audit: `appointment.no_show`.

### Flow I — Rescheduling
Trigger: `POST …/{id}/reschedule` (`:399`). Replacement appointment inherits `lead_id`; lead stays `appointment_booked`; both rows show in appointment history + two `appointment_history` rows (existing `:438`). No lead stage change.

### Flow J — Lost and reopened
Lost: `PATCH status=lost` + `lost_reason` *(reuse)*. Reopen: `PATCH status∈{new,contacted}` *(modified: clears `lost_reason`)*; `lead.manage`. Both write stage history.

### Flow K — Follow-up task
UI: lead detail → add task (description, due, assignee). → `POST /api/v1/leads/{id}/follow-ups` *(new)*; list `GET …/follow-ups` *(new)*; complete/cancel `PATCH …/follow-ups/{id}` *(new)*. "Overdue" derived. Completion writes a `lead_activities` row. RBAC: `lead.manage`.

### Flow L — Duplicate detection
UI: entering phone/email in New Lead or Convert → call `duplicate_candidates` (existing patient endpoint `crm/routes.py:263`) and a **new** lead-candidates lookup (active same-clinic leads by normalized email/phone). Show candidates; user selects existing or proceeds with an explicit new enquiry. On convert, a conflicting match returns `DUPLICATE_REVIEW_REQUIRED` and the UI presents the picker. No global unique constraint (ADR 0001). RBAC: `lead.read`/`patient.read`.

---

## 10. Data model and relationships

**Existing (unchanged):** `leads`, `lead_activities`, `appointments`, `appointment_history`, `patients`, `follow_up_tasks` (patient-only).

**RECOMMENDATION — changes:**
1. `appointments.lead_id uuid NULL` + composite FK `(clinic_id, lead_id)→leads` `ON DELETE SET NULL` + index. (One-to-many lead→appointments; single source of truth.)
2. `leads.capture_method text NOT NULL DEFAULT 'manual_staff_entry'` + `CHECK in ('manual_staff_entry','public_website_form','custom_website_form','import','other')`. Optionally constrain `source` to `('phone_call','walk_in','referral','website','social_media','import','other')` via CHECK (keep it separate from capture method).
3. `lead_follow_ups` table (Section 8) — RLS-forced, runtime `SELECT/INSERT/UPDATE`.
4. `lead_stage_history` table: `id, clinic_id, lead_id, from_status, to_status, actor_user_id NULL, reason NULL, created_at` + composite FK to `leads`, RLS-forced, runtime `SELECT/INSERT`, index `(clinic_id, lead_id, created_at DESC, id DESC)`. Mirrors `appointment_history`.
5. (Final phase) drop `leads.appointment_id` after readers use `appointments.lead_id`.

`converted_to_patient_id` stays as the single conversion pointer (not reused for association). `merge.py` and `reconcile_merges.py` continue to repoint it; **no new patient-pointer column** is added to leads, so merge wiring is unchanged.

---

## 11. API contract and endpoints

| Endpoint | Change | Permission | Tenant | Key errors | Txn |
|---|---|---|---|---|---|
| `POST /api/v1/leads` | **modify**: scope validation + `capture_method` | `lead.manage` | scoped | `INVALID_INPUT`, `FORBIDDEN` | single |
| `PATCH /api/v1/leads/{id}` | **modify**: drop `visited` auto-convert; exclude event-only statuses; reopen clears `lost_reason`; write stage history | `lead.manage` | scoped | `VERSION_CONFLICT`, `INVALID_TRANSITION`, `LEAD_CONVERTED` | single |
| `POST /api/v1/leads/{id}/convert` | **modify**: `lead.convert`; shared resolver; no auto-trigger | `lead.convert` | scoped | `DUPLICATE_REVIEW_REQUIRED`, `NOT_FOUND`, `LEAD_CONVERTED` | single + `FOR UPDATE` |
| `GET /api/v1/leads/{id}/appointments` | **new**: list linked appointments | `lead.read` | scoped | `NOT_FOUND` | read |
| `GET/POST /api/v1/leads/{id}/follow-ups`, `PATCH …/follow-ups/{fid}` | **new**: actionable tasks | `lead.read`/`lead.manage` | scoped | `VERSION_CONFLICT`, `NOT_FOUND` | single |
| `GET /api/v1/leads/{id}/history` | **new**: stage history | `lead.read` | scoped | `NOT_FOUND` | read |
| `GET /api/v1/leads/duplicate-candidates` | **new**: lead-side candidate lookup | `lead.read` | scoped | — | read |
| `POST /api/v1/appointments` | **modify**: accept `lead_id`; shared resolver; link + advance lead in txn | `appointment.create` | scoped | `APPOINTMENT_CONFLICT`, `DUPLICATE_REVIEW_REQUIRED`, `IDEMPOTENCY_MISMATCH` | booking txn |
| `POST /api/v1/appointments/{id}/status` | **modify**: on `arrived`+`lead_id` → lead `visited` (idempotent) | `appointment.check_in` | scoped | `INVALID_TRANSITION`, `VERSION_CONFLICT` | single |
| cancel / no_show / reschedule handlers | **modify**: lead return-to-qualified + follow-up; reschedule inherits `lead_id` | per existing | scoped | existing | single |
| Public intake (`websites`, `website_content`) | **reuse** (set `capture_method` accordingly) | public | slug-scoped | existing | single |

Envelopes stay `{"data": …}` / `{"error": {...}}`; cursor pagination; `X-CSRF-Token` + origin validation on writes (`_write_authorized`). Regenerate `packages/contracts/openapi.json` + `openapi-types.ts` and assert no drift.

---

## 12. UI/UX design

Use the existing care/fully design system (`globals.css` tokens, `surface-card`, `pipeline-*`, drawers/toast/confirm in `_lib/`). Do not redesign unrelated CRM screens.

- **Leads overview:** pipeline summary (counts per stage), stage tabs (existing), search, owner filter, branch/specialty filter, acquisition-source filter, date filter, **overdue-follow-up filter**, **unassigned filter**, Archived.
- **New lead form:** minimal; **acquisition source** and **capture method** are separate fields (capture method defaults to Manual Staff Entry and is read-only for staff entry); scope-aware specialty/branch/assignee dropdowns; inline duplicate warning (Flow L). Remove "website" from the manual *source*... (acquisition "website" stays valid, but capture method is manual).
- **Lead row/card:** name, contact, stage, owner, branch, specialty, source, last activity, next follow-up (with overdue badge), appointment status, patient relationship.
- **Lead detail (`[leadId]/page.tsx`):** contact, current stage, owner, **appointment history** (new list), patient association, activities, **follow-up tasks** (new, with complete/cancel), lost reason, **stage history** (new). Convert button uses `lead.convert` and prefills the associated patient.
- **Appointment drawer:** `AddAppointmentDrawer` gains an optional `leadId` prop; when launched from a lead it is passed through to the booking POST (so the link persists) while keeping the existing standalone-booking path unchanged. Lead context banner shown; no other workflow change.
- **Desktop + mobile:** cards collapse to single column; drawers full-height on mobile; 16px gutters; no horizontal scroll (existing patterns).

No decorative features without a workflow purpose.

---

## 13. Permissions and scope

- **FACT:** registry has `lead.read`, `lead.manage` (`permissions.py:52-53`); appointment perms incl. `appointment.create`, `appointment.check_in` (`:15-21`).
- **RECOMMENDATION:** add `lead.convert` to the `PERMISSIONS` registry **and** grant it (owner + manager, mirroring `report.manage` precedent) in the same migration — `require_permission` validates against the registry, so a DB grant alone is insufficient (lesson from `.claude/WORK_STATE.md`). `lead.read`/`lead.manage` cover everything else incl. follow-ups.
- **Scope:** reuse `_LEAD_SCOPE_SQL` (specialty+branch); add the same scope check to `lead_create` (D7). New tables are tenant-forced RLS; the follow-ups/history/appointments lists all go through `_require_lead` first. Unassigned (NULL branch/specialty) leads stay visible to unscoped triage users, as today (`0093`).

---

## 14. Migration plan

Chain after the current head on the implementation branch (**FACT:** head on `fix/contract-drift-regen` is `0097_saved_reports`; `main` additionally has `0098_access_requests` — rebase and number accordingly; do not hardcode a number). `env.py` already ensures `alembic_version` is `varchar(64)`.

1. **M1 `appointments.lead_id`** — add nullable column + composite FK + index. No backfill (historical appointments had no link; dead `leads.appointment_id` values can optionally be backfilled onto `appointments.lead_id` in the same migration: `UPDATE appointments a SET lead_id = l.id FROM leads l WHERE l.appointment_id = a.id AND l.clinic_id = a.clinic_id`). Additive, reversible.
2. **M2 `leads.capture_method`** — add column `NOT NULL DEFAULT 'manual_staff_entry'` + CHECK; **backfill** existing rows: `capture_method = 'public_website_form' WHERE source='website' ELSE 'manual_staff_entry'`. (Optional) add `source` CHECK after normalising legacy values. Reversible.
3. **M3 `lead_follow_ups`** — create table + RLS (ENABLE+FORCE+policy) + runtime grants + indexes.
4. **M4 `lead_stage_history`** — create table + RLS + grants + index. Optionally backfill one `{to_status=status}` row per existing lead for continuity.
5. **M5 `lead.convert` permission** — register in `permissions.py` + grant to owner/manager roles.
6. **M6 (final, after readers migrated) drop `leads.appointment_id`** — only after `_LEAD_SCOPE_SQL` and the detail read use `appointments.lead_id`. Its FK is `ON DELETE SET NULL`, so dropping is safe; keep as a separate, late, reversible migration.

Verify each on a **clean** DB (`alembic upgrade head`) and on a **populated** copy of `healthcare_test` (backfills correct), per `[[test-db-setup]]`. No destructive changes; M6 is the only drop and is deferred + guarded.

---

## 15. Implementation phases (sequencing & critical path)

Database/domain correctness before frontend polish. Each phase is independently reviewable and shippable.

- **Phase 1 — Linkage foundation (critical path):** M1 (`appointments.lead_id`), shared `resolve_patient` (fix D4), booking accepts `lead_id` and advances lead in-txn (Flow D), stage-history table M4 + writes. Backend tests. *No UI yet.*
- **Phase 2 — Attendance + lifecycle correctness:** arrival→visited hook (Flow E), remove `visited` auto-convert (D2), decouple association-freeze (D3), cancel/no_show return-to-qualified + reschedule inheritance (Flows G/H/I), transition-matrix update (Section 6), reopen clears `lost_reason`.
- **Phase 3 — Conversion & scope:** `lead.convert` permission M5 (Flow F), scope validation on create (D7), lead duplicate-candidates endpoint (Flow L).
- **Phase 4 — Attribution:** M2 `capture_method` + public-intake labelling + manual-form split (D6).
- **Phase 5 — Follow-ups:** M3 `lead_follow_ups` + endpoints (Flow K); follow-up creation on cancel/no_show.
- **Phase 6 — Frontend:** overview filters, detail page (appointment history, follow-ups, stage history), drawer `leadId` wiring, convert UX; Playwright specs.
- **Phase 7 — Cleanup:** switch readers to `appointments.lead_id`, then M6 drops `leads.appointment_id`; contract regen + drift check.

Dependencies: Phase 1 gates 2, 3, 5, 6. Phase 7 gates on 1+6. Phase 4 is independent (can parallelise).

---

## 16. Test strategy

Integration tests run against real RLS (`TEST_ADMIN_DATABASE_URL` + `TEST_DATABASE_URL`, `[[test-db-setup]]`); mocked 200s are not proof.

| Area | Setup | Action | Expected DB | Expected API | Security assertion |
|---|---|---|---|---|---|
| Manual intake | staff session | `POST /leads` | row, `capture_method='manual_staff_entry'` | 201 | out-of-tenant clinic_id invisible |
| Scope on create (D7) | branch-scoped user, out-of-scope branch | `POST /leads` | no row | 403 | cannot create self-invisible lead |
| Duplicate warning | existing patient same phone | candidates lookup / convert | — | candidates / `DUPLICATE_REVIEW_REQUIRED` | no cross-tenant candidates |
| Lifecycle manual | lead `new` | `PATCH` event-only target | unchanged | `INVALID_TRANSITION` | staff cannot fake booked/visited/converted |
| Appointment linking (D1) | qualified lead | `POST /appointments` w/ `lead_id` | appointment.lead_id set, lead `appointment_booked`, history rows | 201 | foreign lead_id rejected |
| Reschedule (I) | booked lead | reschedule | replacement carries lead_id, lead still booked | 201 | — |
| Cancel/no_show (G/H) | booked lead, single appt | cancel | lead→`qualified`, follow-up created, **not** lost/visited | 200 | — |
| Arrival (E) | booked lead | `status=arrived` | lead→`visited` once; replay no-op | 200 | — |
| No auto-convert (D2) | lead reaches visited | — | `converted_to_patient_id` still NULL; status `visited` | — | — |
| Association ≠ terminal (D3) | visited lead | `PATCH`/convert | movable; convert sets converted | 200 | — |
| Patient matching (D4) | email→A, phone→B | internal booking | `DUPLICATE_REVIEW_REQUIRED`; no silent attach; never archived/merged patient | 409 | — |
| Conversion (F) | visited lead, valid patient | `/convert` | `converted`, pointer set, idempotent replay | 200 | requires `lead.convert` |
| Concurrency | two convert calls | parallel | one wins, one idempotent | 200/200 | no duplicate patient |
| Follow-ups (K) | lead | create/complete/cancel | status transitions, completed_at, activity row | 201/200 | RLS-isolated |
| RBAC | user lacking `lead.convert` | `/convert` | no change | 403 | — |
| Tenant isolation | foreign clinic | all lead endpoints | no rows | 404/403 | negative-control test |
| Public intake | website form | submit | lead `capture_method='public_website_form'`, idempotent | 201 | unchanged behaviour |
| Existing appt/patient flows | `lead_id IS NULL` | book/cancel/convert patient | unchanged | unchanged | regression guard |
| Mobile UI | Playwright viewport | detail + drawer | renders, no horizontal scroll | — | — |
| Migrations | clean + populated DB | `upgrade head` | backfills correct; `downgrade` clean | — | forced-RLS test passes on new tables |

Do not delete existing lead specs (`test_lead_*`, `lead-timeline.spec.ts`); update expectations where semantics change (e.g. `visited` no longer converts).

---

## 17. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Changing conversion semantics breaks funnel metric (`operations/routes.py:286-287`) | Keep `converted_to_patient_id` = conversion only; association is derived, not stored → metric meaning preserved. Add a regression test on the funnel. |
| `GROUP BY l.status` demand breakdown (`:227`) | Status vocabulary unchanged → query unaffected. |
| Dropping `leads.appointment_id` breaks scope sub-query (`:47-51`) / detail read | Deferred to Phase 7; readers switched to `appointments.lead_id` first; FK is `ON DELETE SET NULL`. |
| Merge/reconcile must cover lead↔patient | No new patient pointer added; `merge.py:128-131` + `reconcile_merges.py:36` already cover `converted_to_patient_id`. |
| New tables missing forced RLS | `test_every_clinic_owned_table_has_forced_rls` will fail the build until ENABLE+FORCE+policy added. |
| Public booking can't show a 409 picker | Public path creates a fresh patient on conflict + enqueues reconcile marker; never silently attaches to ambiguous/archived records. |
| Concurrent conversion duplicates patients | `FOR UPDATE` on lead (`:384`) + `converted_to_patient_id IS NULL` guard (`:405`) + shared resolver; soft-gate per ADR 0001. |
| Contract drift | Regenerate `openapi.json`/types; `git diff --exit-code packages/contracts/`. |
| Alembic numbering (branch vs main) | Rebase onto the real head before numbering migrations; `env.py` handles `version_num` length. |

---

## 18. Definition of done

- All 8 defects (D1–D8) closed, each with an integration test proving the fix against real RLS.
- Booking from a lead persists `appointments.lead_id` and advances the lead; arrival (not booking) sets `visited`; conversion is explicit and separately permissioned; no auto-convert anywhere.
- One shared, safe patient resolver; no `LIMIT 1` arbitrary attach; never attaches to archived/merged patients.
- `lead_follow_ups` + `lead_stage_history` live, RLS-forced; `lead_activities` still immutable.
- `capture_method` split; public + custom website intake still work and are correctly labelled; manual leads never labelled website.
- Scope-safe create; existing non-lead appointment and patient flows regression-green.
- Backend suite green (integration incl.), web `tsc` clean, `eslint` zero warnings, Playwright green, contract no-drift, migrations clean on empty **and** populated DBs.
- Tenant isolation negative controls pass; audit events present for every stage change.

---

## 19. Classification table

| Item | Type | Evidence / Note |
|---|---|---|
| `leads.appointment_id` never written; booking never links/advances lead | **Confirmed defect (D1)** | `0046:93,104`; `blueprint_core/routes.py:144,167`; no `appointments.lead_id`; `add-appointment-drawer.tsx:188-212` |
| `visited` auto-creates patient + `lead.convert` audit | **Confirmed defect (D2)** | `blueprint_core/routes.py:244-252,262-263` |
| Patient-associated lead frozen (no status change, no archive) | **Confirmed defect (D3)** | `:202-205,:420` |
| Booking resolves patient `LIMIT 1`, no archived/duplicate filter | **Confirmed defect (D4)** | `appointments/routes.py:497,887` |
| No actionable lead follow-up model | **Confirmed defect (D5)** | `0057:50`; `follow_up_tasks` patient-bound `0007` |
| Source vs capture method conflated; manual can be "website" | **Confirmed defect (D6)** | `0046:86`; `websites/routes.py:62`; `website_content/routes.py:142`; `leads/page.tsx:25` |
| `lead_create` lacks scope validation (self-invisible leads) | **Confirmed defect (D7)** | `:178-188` vs `:211-236` + `:33-54` |
| No lead stage-history table; reopen keeps `lost_reason`; no `lead.convert` perm | **Confirmed defect (D8)** | no migration; `permissions.py:52-53`; `leads/page.tsx:133` |
| `appointments.lead_id` one-to-many link | **Proposed improvement** | Section 7.1 |
| Shared `resolve_patient` service | **Proposed improvement** | Section 7.2 |
| Association derived (not stored) vs conversion pointer | **Proposed improvement** | Section 7.3 |
| `lead_follow_ups`, `lead_stage_history`, `capture_method` | **Proposed improvement** | Sections 8, 10 |
| Keep 7-status vocabulary (no rename) | **Existing behaviour to preserve** | `0046:100`; `operations/routes.py:227` |
| Soft-duplicate gate (no unique email/phone index) | **Existing behaviour to preserve** | ADR 0001 |
| Public + custom website intake | **Existing behaviour to preserve** | `websites/routes.py`, `website_content/routes.py` |
| Immutable `lead_activities` | **Existing behaviour to preserve** | `0057:50` |
| Merge/reconcile repointing `converted_to_patient_id` | **Existing behaviour to preserve** | `crm/merge.py:128-131`; `reconcile_merges.py:36` |
| Reschedule supersedes-chain | **Existing behaviour to preserve** | `appointments/routes.py:428-438` |
| `source` acquisition vocabulary (free-text vs CHECK) | **Needs clarification** | Section 10 — constrain or keep free-text? |
| Public-path conflict policy (create-new vs skip) | **Needs clarification** | Section 7.2 — confirm "create new + reconcile marker" is acceptable |
| Backfill `lead_stage_history` for existing leads | **Needs clarification** | Section 14 M4 — one synthetic row per lead, or start empty? |
| Should `visited` also fire on `completed` if `arrived` was skipped? | **Needs clarification** | Some flows jump states; confirm `arrived` is the sole visit trigger |

---

## 20. Implementation decisions (resolved during execution)

The four "Needs clarification" items were resolved with safe, backward-compatible defaults and implemented:

1. **`source` stays free-text; a new constrained `capture_method` carries the CRM channel.** A `CHECK` on `source` would have to reject or migrate arbitrary historical values, so acquisition `source` is left free-text and `leads.capture_method` (migration `0102`, `CHECK IN ('manual_staff_entry','public_website_form','custom_website_form','import','other')`) records how the lead entered. Manual entry forces `manual_staff_entry`; the public form → `public_website_form`; the custom form builder → `custom_website_form`. Existing `source='website'` rows backfill to `public_website_form`.
2. **Public (non-interactive) patient conflicts create a fresh patient; staff (interactive) conflicts raise `DUPLICATE_REVIEW_REQUIRED`.** `crm.identity.resolve_patient(..., interactive=...)` never silently attaches to one of two conflicting matches and never matches archived/merged records (ADR 0001 soft-gate + reconcile remain the dedup path).
3. **`arrived` is the sole, idempotent visit trigger.** `mark_lead_visited` only advances a lead from `appointment_booked`, so later progress (`waiting`/`in_consultation`/`completed`) never re-fires a visit and a booking is never counted as a visit.
4. **`lead_stage_history` is backfilled one row per existing lead** (migration `0100`, `to_status = current status`, timestamped at the lead's creation) so the new timeline is populated for pre-existing leads.

The deferred `leads.appointment_id` cleanup (plan §7.1 / §15 Phase 7) was completed: all readers moved to `appointments.lead_id` and the dead scalar was dropped in migration `0104`.

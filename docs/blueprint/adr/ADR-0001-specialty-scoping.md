# ADR-0001: Specialty is a clinic-scoped dimension, alongside branch scope

- Status: proposed — pending human review
- Date: 2026-09-30
- Scope: blueprint §§3.1, 3.2, 6, 14.2

## Context

The current tenant key is `clinic_id`; branches and users already have tenant and branch scope through forced RLS and authorization predicates. `doctor_profiles.specialty` is only free text. The blueprint requires one clinic to operate several specialties while sharing patients, billing, staff where permitted, and reporting.

## Decision

Keep `clinic_id` as the sole tenant boundary. Add a platform specialty registry and a clinic-specialty enablement relationship. Specialty becomes a first-class authorization/filter dimension alongside branch, not a replacement tenant key and not a second tenant hierarchy. Services, providers, appointments, treatment records, leads, website references, reports, and user grants may carry a specialty key where the concept is meaningful. A record that is clinic-wide remains clinic-wide; it is not forced into a specialty.

Authorization evaluates: tenant → module/action → branch scope (when applicable) → specialty scope (when applicable) → sensitivity/object scope. Every specialty relationship has a same-clinic composite FK and RLS follows the existing transaction-local `app.clinic_id` pattern. Existing rows migrate with a deliberate default/nullable policy decided per table; no implicit free-text specialty comparison is authoritative.

## Alternatives rejected

- Make each specialty a separate clinic tenant: duplicates patients, billing, staff, websites, and reporting, violating the one-account/one-patient blueprint.
- Put specialty only in plan feature codes: limits would not provide data authorization or record-level filtering.
- Treat specialty as text on providers/services: cannot safely enforce enabled-specialty or user-specialty scope.

## Consequences

RLS policies and repository predicates gain specialty-aware joins where needed. Existing branch-only scopes remain valid for clinic-wide records. A clinic can enable a new specialty without migrating to a new tenant, and the upgrade request can activate the same clinic-specialty relationship. Specialty-specific clinical fields remain modular and do not contaminate the shared patient identity.

## Non-goals

This ADR does not add a migration or implement specialty access. It does not change the existing appointment state machine or tenant context contract.

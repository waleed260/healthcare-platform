# ADR-0004: Clinics receive editable copies of platform master services

- Status: Accepted — approved by human owner on 2026-09-30
- Date: 2026-09-30
- Scope: blueprint §7.1

## Decision

Maintain platform-owned master service templates separately from clinic-owned `services`. Selecting a template copies its current fields into a new clinic service and records the source template/version. There is no live read-only reference. Clinic edits—including name, price, duration, tax, booking rules, specialty fields, and website visibility—belong to the clinic copy. Later master changes do not overwrite clinic data; the platform may offer an explicit review/update action in a future workflow.

Custom services are clinic-owned rows with no master source. All copied/custom services remain under the current tenant, branch assignment, provider assignment, permission, RLS, and appointment snapshot rules.

## Alternatives rejected

- Read-only reference with overrides: makes provenance and conflict resolution harder and risks changing clinic behavior when a template changes.
- Mutate the master row per clinic: breaks tenant isolation and makes platform catalog governance impossible.

## Consequences

Onboarding becomes select → copy → customize. Dynamic websites read the clinic service copy, so CRM remains the source of truth. Master catalog versioning is platform scope; clinic service history is tenant scope.

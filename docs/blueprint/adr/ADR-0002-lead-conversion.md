# ADR-0002: Leads are a separate pipeline entity with a patient conversion link

- Status: proposed — pending human review
- Date: 2026-09-30
- Scope: blueprint §9.1 and §22.2

## Decision

Create a tenant-scoped `leads` domain separate from `patients`. A lead stores prospect identity/contact data, source/campaign, requested specialty/service, owner, pipeline status, activity/follow-up data, and optional appointment linkage. Conversion is a transactional command that resolves duplicate candidates, creates or selects exactly one patient, writes `converted_to_patient_id`, and retains the lead history. It never creates a second patient for the same conversion.

Patient status is not overloaded to represent pre-patient sales stages. Existing duplicate-review and merge controls remain the patient identity safety net. A converted lead remains queryable for attribution but is no longer an active pipeline item.

## Alternatives rejected

- Add `lead` statuses to `patients`: creates incomplete patient records, mixes sales and clinical privacy, and cannot represent an unconverted prospect cleanly.
- Delete leads on conversion: loses source, campaign, activity, and audit history.

## Consequences

Website forms, manual entry, imports, and appointment requests write leads through a single domain. Appointment linkage is nullable and tenant-safe. Reporting can measure funnel conversion without treating marketing data as a medical record. Lead access receives its own permissions and specialty/branch filters.

## Non-goals

No lead tables/routes/UI are introduced in Phase 0.

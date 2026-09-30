# ADR-0006: Specialty locking and upgrade requests extend the existing plan control plane

- Status: Accepted — approved by human owner on 2026-09-30
- Date: 2026-09-30
- Scope: blueprint §§4.2–4.4 and §23

## Decision

Keep `plans`, `feature_limits`, `clinic_subscriptions`, and `clinic_feature_usage` as the platform control plane. Represent specialty allowance as feature-limit data (for example a maximum enabled-specialty count and/or an allowlist), while the clinic-specialty relationship from ADR-0001 is the authoritative current access state. Do not add plan-specific specialty columns or duplicate subscription tables.

Add a tenant-scoped upgrade-request workflow with status, requested specialty/feature, requester, review decision, commercial notes, and audited approver. Approval changes the subscription/limit and then activates the clinic capability in one controlled workflow; decline leaves the existing access unchanged. Feature gates are enforced server-side in addition to UI locked states.

## Alternatives rejected

- Encode every specialty as a separate plan column: not configurable and makes future specialties migrations.
- Treat a UI lock as access control: violates the existing authorization contract.
- Replace current plan tables: discards working governance and usage foundations.

## Consequences

Platform admins continue to manage plans and limits from existing governance surfaces. Clinic upgrade requests become a new auditable governance workflow. Billing/commercial terms can evolve without changing tenant data shape.

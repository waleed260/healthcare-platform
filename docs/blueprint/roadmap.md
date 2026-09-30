# Blueprint reconciliation roadmap

Status: proposed sequence; names and order only. Each future goal is intended to be a 5–7 day vertical slice with one deliverable, a day-3 checkpoint, and explicit DONE WHEN evidence. No implementation goals are opened by this Phase 0 document.

## Phase 1 — Core SaaS

1. **Specialty-aware tenant and authorization foundation** — ADR-0001 and ADR-0007; clinic specialty enablement, membership/context model, specialty-aware scope predicates, and migration/denial evidence.
2. **Master service catalog and multi-specialty onboarding** — ADR-0004; platform templates, clinic copies, custom services, and onboarding selection flow.
3. **Lead pipeline and lossless lead-to-patient conversion** — ADR-0002; capture, pipeline, ownership, appointment linkage, dedupe, conversion, and audit.
4. **Patient treatment-plan and clinical foundation** — ADR-0005; treatment plans, notes/forms/prescriptions, consent linkage, and appointment conversion without changing appointment integrity.
5. **Patient billing skeleton and receipt contract** — ADR-0003; invoices, partial payments, balances, numbering, audit, and printable receipt data.
6. **Core clinic and platform reporting** — specialty-aware dashboard aggregates for appointments, patients, leads, revenue, payments, and operational health.

## Phase 2 — Website Platform

7. **Structured editor expansion and theme system** — page/section/block library, global theme, header/footer, responsive editing, and safe schema validation.
8. **CRM-powered dynamic website surfaces** — service, provider, branch, booking, and approved-media references with tenant/specialty filtering.
9. **Website forms to lead/appointment intake** — configurable form fields, consent, routing, notifications, and idempotent CRM intake.
10. **Template, media, SEO, and domain operations** — specialty templates, media organization, SEO metadata, optimization, domains, and plan gates.

## Phase 3 — Advanced Operations

11. **Packages and treatment-session consumption** — package purchase, entitlement ledger, appointment linkage, progress, expiry, and authorized overuse override.
12. **Inventory and service consumption** — products/consumables, branch stock, adjustments, low-stock alerts, and audit.
13. **Advanced financial and operational reporting** — aging, payment methods, provider commissions, package utilization, inventory, funnel, and specialty/branch cuts.
14. **Specialty clinical workflow packs** — dental, hair, skin, dermatology forms and media workflows, plugged into the shared patient/treatment model.

## Phase 4 — Growth & Integrations

15. **External communications and automation** — reminders, messaging integrations, campaign attribution, and event-driven automation.
16. **Analytics, pixels, APIs, and webhooks** — plan-gated integrations with consent, secrets, audit, and delivery/replay controls.
17. **Additional specialties and enterprise controls** — new specialty packs, advanced support/commercial controls, retention/export policy, and enterprise administration.

## Sequencing gates

- Phase 1 cannot start until all ADRs in `docs/blueprint/adr/` are human-approved.
- No future goal may alter the unchanged systems listed in `gap-matrix.md` without a new ADR and regression evidence.
- Each vertical slice must preserve forced RLS, composite tenant relationships, server-side authorization, auditability, cursor/API contracts, and the appointment state/concurrency contract.

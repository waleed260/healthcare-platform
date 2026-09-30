# Blueprint reconciliation review index

Phase 0 is documentation-only. No blueprint feature, migration, endpoint, or UI may be implemented by this goal. All seven ADRs require explicit human review before a separate Phase 1 implementation goal.

## Approval checklist

| Required decision | ADR | Review status |
|---|---|---|
| Specialty as clinic-scoped dimension alongside branch | [ADR-0001](adr/ADR-0001-specialty-scoping.md) | Accepted 2026-09-30 |
| Separate leads entity and non-duplicating conversion | [ADR-0002](adr/ADR-0002-lead-conversion.md) | Accepted 2026-09-30 |
| Currency, tax, invoice numbering, and partial payments | [ADR-0003](adr/ADR-0003-patient-billing.md) | Accepted 2026-09-30 |
| Platform master catalog copied into editable clinic services | [ADR-0004](adr/ADR-0004-master-catalog-copy-on-select.md) | Accepted 2026-09-30 |
| Treatment/package session ledger linked to appointments | [ADR-0005](adr/ADR-0005-treatment-session-ledger.md) | Accepted 2026-09-30 |
| Existing plans/feature limits extended for specialty locks/upgrades | [ADR-0006](adr/ADR-0006-plan-feature-limits-extension.md) | Accepted 2026-09-30 |
| Multi-clinic memberships with one active server-side context | [ADR-0007](adr/ADR-0007-multi-context-identity.md) | Accepted 2026-09-30 |

## Supporting artifacts

- [Gap matrix](gap-matrix.md) — every Section 3.2 entity and Sections 4–24 capability mapped to current evidence and future direction.
- [Sequencing roadmap](roadmap.md) — ordered goals across Core SaaS, Website Platform, Advanced Operations, and Growth & Integrations.

## Approval action

The owner must explicitly approve or request revisions to each ADR. Approval is a gate for the separate Phase 1 implementation goal; it does not authorize implementation within Phase 0.

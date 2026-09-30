# Blueprint reconciliation review index

Phase 0 is documentation-only. No blueprint feature, migration, endpoint, or UI may be implemented by this goal. All seven ADRs require explicit human review before a separate Phase 1 implementation goal.

## Approval checklist

| Required decision | ADR | Review status |
|---|---|---|
| Specialty as clinic-scoped dimension alongside branch | [ADR-0001](adr/ADR-0001-specialty-scoping.md) | Pending human review |
| Separate leads entity and non-duplicating conversion | [ADR-0002](adr/ADR-0002-lead-conversion.md) | Pending human review |
| Currency, tax, invoice numbering, and partial payments | [ADR-0003](adr/ADR-0003-patient-billing.md) | Pending human review |
| Platform master catalog copied into editable clinic services | [ADR-0004](adr/ADR-0004-master-catalog-copy-on-select.md) | Pending human review |
| Treatment/package session ledger linked to appointments | [ADR-0005](adr/ADR-0005-treatment-session-ledger.md) | Pending human review |
| Existing plans/feature limits extended for specialty locks/upgrades | [ADR-0006](adr/ADR-0006-plan-feature-limits-extension.md) | Pending human review |
| Multi-clinic memberships with one active server-side context | [ADR-0007](adr/ADR-0007-multi-context-identity.md) | Pending human review |

## Supporting artifacts

- [Gap matrix](gap-matrix.md) — every Section 3.2 entity and Sections 4–24 capability mapped to current evidence and future direction.
- [Sequencing roadmap](roadmap.md) — ordered goals across Core SaaS, Website Platform, Advanced Operations, and Growth & Integrations.

## Approval action

The owner must explicitly approve or request revisions to each ADR. Approval is a gate for the separate Phase 1 implementation goal; it does not authorize implementation within Phase 0.

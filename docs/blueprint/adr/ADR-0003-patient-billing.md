# ADR-0003: Patient billing uses clinic-scoped invoices plus an append-only payment ledger

- Status: proposed — pending human review
- Date: 2026-09-30
- Scope: blueprint §12 and §23

## Decision

Patient billing is separate from SaaS subscription billing. Add clinic-scoped invoices, invoice lines, payments, payment allocations, refunds/void records, and receipt metadata. Invoices may reference a patient, treatment plan item, appointment, service, or package. Payment allocations support full and partial settlement from day one; balance is derived from totals and allocations, with explicit refund/void adjustments rather than destructive edits.

The clinic has a configured default ISO currency and timezone; every invoice and payment stores its currency. Multi-currency conversion is out of scope until a later ADR. Tax is represented as explicit line/header amounts with a configurable tax policy snapshot; tax registration/filing is not delegated to this schema. Invoice numbering is clinic-scoped, concurrency-safe, immutable after issuance, and formatted from a configurable prefix/year/sequence, e.g. `CLINIC-2026-001283`. SaaS plan prices remain in the platform billing domain and are not patient invoices.

Invoice/payment mutations are transactional, idempotent, audited, permission-protected, and preserve historical price/tax snapshots. Receipts render from the persisted invoice/payment snapshot in A4 and 80mm formats.

## Alternatives rejected

- Single payment column on appointments/patients: cannot represent partial payments, allocations, refunds, or audit history.
- Reuse `clinic_subscriptions`: conflates platform revenue with clinic/patient receivables.
- Defer currency/tax choices: makes invoice numbering and amount semantics unstable during the first schema design.

## Consequences

Financial reporting can derive paid, partial, unpaid, refunded, aging, cashier, method, provider, branch, and specialty views. Authorization must separate clinical access from financial access. Exact tax/legal requirements remain deployment-specific and require later policy configuration.

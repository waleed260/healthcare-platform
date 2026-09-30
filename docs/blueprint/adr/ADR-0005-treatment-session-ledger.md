# ADR-0005: Package and treatment sessions use a separate session ledger linked to appointments

- Status: Accepted — approved by human owner on 2026-09-30
- Date: 2026-09-30
- Scope: blueprint §§8, 11, 12

## Decision

Create first-class treatment plans, treatment plan items, package entitlements, and treatment-plan sessions. A session may reference one appointment, service, provider, branch, and consumption event. The existing appointment remains the scheduling/occupancy and lifecycle record; it is not repurposed to hold package balances or treatment-plan state. Session consumption is an audited, transactional ledger operation that prevents overuse by default and supports an explicit authorized override.

Invoices and payments reference the package or treatment-plan purchase. Appointment creation may reserve or link a planned session, while completion consumes it according to a policy defined by the treatment domain. Cancellation/no-show behavior must be explicit and cannot bypass the appointment state machine.

## Alternatives rejected

- Store session count on `appointments`: does not represent a multi-visit purchase or remaining balance and makes rescheduling unsafe.
- Add a mutable sessions counter to `patients`: loses service/package/provider/branch provenance.

## Consequences

Package progress is visible on the patient profile and reportable by specialty/service/provider/branch. The domain can mature independently of appointment concurrency. Inventory consumption remains a later extension.

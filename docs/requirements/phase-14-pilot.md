# Phase 14 controlled pilot

Phase 14 is an operational release activity, not a code-only completion state.
This record is intentionally blank until a synthetic-data staging deployment is
exercised by the release owner and a pilot clinic owner approves the workflow.

## Entry criteria

The release owner must attach the Phase 13 evidence manifest and confirm that
the fail-closed validator passes. The pilot environment must use synthetic
clinics, staff, patients, appointments, documents, and website content only.
Production records, credentials, tokens, signed URLs, and screenshots containing
patient content must not be copied into the pilot evidence bundle.

| Entry check | Evidence | Status |
| --- | --- | --- |
| Phase 13 release manifest passes | Restricted manifest path and validator output | [ ] |
| Deployment version and migration head recorded | Deployment and schema identifiers | [ ] |
| Backup restore and isolation evidence attached | Restore record, row counts, RLS checks | [ ] |
| WCAG and performance evidence attached | Automated results and manual review | [ ] |
| On-call, rollback, scanner, storage, and TLS owners assigned | Runbook links and names | [ ] |

## Synthetic pilot workflow

Run each flow in a fresh browser session at desktop and tablet widths. Record
the deployment version, UTC start/end time, browser/assistive technology, test
fixture namespace, and defect IDs. The workflow must be repeatable without
real patient data.

| Flow | Required outcome | Result / defect |
| --- | --- | --- |
| Clinic onboarding and resume | Owner can save a partial setup, resume it, and complete it | [ ] |
| Public booking | Availability respects hours, buffers, holidays, DST, limits, and idempotency | [ ] |
| Reception and queue | Staff can check in, start, and complete a scoped appointment on tablet | [ ] |
| CRM privacy | Patient search, note visibility, consent, archive, and object scope behave correctly | [ ] |
| Private documents | Pending/quarantined files cannot download; clean files require scoped short-lived access | [ ] |
| Website publishing | Draft, sanitization, live publish, custom host isolation, and rollback work | [ ] |
| Owner security | MFA enrollment/recovery, session rotation, manual reset, and revocation work | [ ] |
| Support access | Explicit approval, reason, permissions, expiry, revocation, and audit evidence are present | [ ] |

## Defect closure and approval

Every failed check must have an owner, severity, remediation, retest result, and
approval to defer. Critical privacy, tenant-isolation, authentication,
appointment-concurrency, backup, or release-gate defects cannot be deferred.

| Defect / check | Severity | Owner | Retest evidence | Disposition |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

| Final acceptance | Approver | UTC date/time | Evidence link |
| --- | --- | --- | --- |
| Release owner confirms runbooks were exercised |  |  |  |
| Pilot clinic owner accepts the operational workflow |  |  |  |
| Incident/rollback contact accepts escalation path |  |  |  |

Phase 14 is complete only when all entry checks and pilot flows pass, critical
defects are closed, and the signed approvals are stored in the restricted
release-evidence location. Until then, the roadmap must continue to report the
phase as open.

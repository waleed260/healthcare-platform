# Phase 12 governance traceability

| Requirement | Evidence |
| --- | --- |
| Plans and feature limits | `0012_governance.py` creates plans, feature limits, and clinic subscriptions with status constraints; `0018_feature_usage.py` and `app/modules/governance/limits.py` enforce configured limits with a race-safe usage ledger |
| Time-limited support access | `support_access_sessions` has explicit reason, approver, permissions, revocation, and a database-enforced maximum 60-minute expiry; platform admins can activate and exit a server-side, expiring support context, and PostgreSQL prevents non-platform sessions from binding one |
| Append-only audit | `audit_events` is tenant-scoped and protected by an immutable database trigger; metadata is size-bounded |
| Privacy requests | `privacy_requests` supports access, correction, deletion, and restriction workflows with patient composite FK; identity verification stores bounded operator evidence and verifier identity |
| Export jobs and retention | `0024_privacy_exports_retention.py` adds tenant-scoped export jobs and explicitly approved retention-policy linkage; `app/modules/governance/jobs.py` generates private, metadata-safe exports, exposes short-lived user-bound access/download commands, and provides tenant-scoped cleanup for expired delivery artifacts |
| Redacted audit helper | `app/modules/audit/service.py` accepts bounded metadata only, does not store request bodies, document contents, tokens, or signed URLs, and links support create/revoke events through `support_session_id` |

Governance commands now expose plan subscription changes, separately approved and
time-limited support access with revocation, audit search, export-job creation,
identity verification, legal-hold-aware erasure, and privacy-request lifecycle
commands. Platform-admin retention APIs separately create inactive policies,
approve them with an auditable operator identity, and assign only active approved
policies to clinics; creation never auto-approves a jurisdictional policy.
Support access is constrained by composite user/clinic FKs and expiry indexes;
approvers must be active, non-archived staff with the support permission; erasure
pseudonymizes direct identifiers and records non-identifying completion evidence.
The platform-admin retention approval surface is available at
`/admin/governance` and keeps create, approve, and clinic assignment as separate
actions with loading, error, retry, and success states. Remaining work is
production export scheduling and the full governance isolation suite. The
clinic `/privacy` workspace provides the corresponding request verification,
approval, execution, and export delivery controls.

The synthetic PostgreSQL isolation matrix now includes privacy-request and
export-job reads plus a cross-tenant export-target write rejection; hosted
execution remains required evidence.

Privacy requests, audit search, and export-job listings use signed cursor pages
with a default limit of 50 and a maximum of 100; audit cursors are bound to the
selected action filter.

Patient privacy requests and patient-access exports reapply the CRM patient
object scope in SQL, including on creation, listing, workflow transitions, and
download-job creation; approved access requests enqueue their export in the same
transaction, and archived patients are not eligible targets.

Platform-admin plan, announcement, and clinic inventory listings use the same
bounded signed-cursor contract and remain available only inside the explicit
platform-admin transaction context.

Migration `0036_platform_admin_context.py` adds an explicit platform-admin flag
and `set_platform_context`; `/api/v1/admin/plans`, plan-limit, announcements,
and clinic inventory endpoints require that context, MFA, and CSRF for writes.
Migration `0037_safe_tenant_policy_cast.py` makes an unset tenant setting fail
closed without invalid UUID-cast errors while permitting only global audit rows
from that explicit platform context.

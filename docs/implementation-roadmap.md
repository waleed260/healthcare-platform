# Healthcare Platform implementation roadmap

Source of truth: `reference/pdfs/Healthcare_Platform_Codex_Implementation_Spec_v2.0.pdf`.

This roadmap preserves the specification's ordered Phase 0–14 plan. A phase is not
complete until its migration, backend authorization, tenant isolation, audit behavior,
frontend states, tests, documentation, and exit gate are evidenced.

| Phase | Scope and requirement families | Exit evidence |
| --- | --- | --- |
| 0 | ADRs, requirements map, threat model, UX flows; TEN/SEC/UX | Decisions approved; unresolved decisions recorded or explicitly deferred |
| 1 | Monorepo, Docker, CI, FastAPI and Next.js shells | Builds, health checks, and test harness pass |
| 2 | PostgreSQL conventions, tenant context, composite keys, forced RLS; TEN/SEC | Two-tenant isolation suite passes before clinical expansion |
| 3 | Argon2id auth, opaque sessions, TOTP, recovery, manual invite/reset, CSRF; AUT/SEC | Revocation, CSRF, rate-limit, MFA, and recovery tests pass |
| 4 | Permission catalog, RBAC, branch scopes, object authorization; RBAC | Every permission-role-object combination has API tests |
| 5 | Clinic onboarding, branches, hours, holidays, doctors, services, rooms/resources; TEN/APT | Setup can be completed and resumed; constraints pass |
| 6 | Controlled websites, editor, sanitization, domains, draft/live, publish/rollback; WEB/UX | Draft/live, sanitization, rollback, and unknown-host tests pass |
| 7 | Availability and appointment engine: DST, buffers, limits, idempotency, concurrency; APT | Availability, overlap, idempotency, and concurrent-booking tests pass |
| 8 | Calendar, queue, follow-ups, notifications, operational dashboard; OPS/UX | Reception critical path works on tablet and respects scope |
| 9 | Patient CRM, duplicates, merge, notes, tags, consent, archive; CRM/SEC | Visibility, merge, archive, and search tests pass |
| 10 | Private documents, public media, quotas, scan/quarantine, signed access; SEC/CRM | Unauthorized, expired, and quarantined downloads fail |
| 11 | Database-backed jobs, due/overdue follow-ups, notifications; OPS/REL | Due/overdue and idempotent jobs pass timezone tests |
| 12 | Plans/limits, support access, audit, privacy requests and retention; TEN/SEC/REL | Limits are transactional; support expires; audit is complete |
| 13 | Hardening, load profile, accessibility, backups/restore, CI/CD and launch gates; SEC/REL/UX | Numeric targets, WCAG checks, restore, security, and release gates pass |
| 14 | Controlled pilot, runbooks, defect closure, owner approval | Runbooks exercised and pilot acceptance recorded |

## Working order

Each vertical slice uses the specification task template: requirement IDs and
dependencies, data contract and migration, authorization and tenant scope, API
errors/idempotency, audit and redaction, UX states, tests, exact commands, and a
completion handoff. No phase is advanced on the basis of a passing unit test alone.

Current repository state: Phases 0–12 have partial implementation and traceability;
the appointment engine now includes explicit DST fold/gap handling, and governance
commands cover subscriptions, separately approved support access, audit search,
export jobs, identity verification, and legal-hold-aware erasure. The later phases
remain open until their full exit gates are verified. Phase 13 now includes a
fail-closed release-evidence validator for that verification.

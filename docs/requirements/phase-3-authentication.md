# Phase 3 authentication traceability

| Requirement | Evidence |
| --- | --- |
| AUT-003 hashed sessions | `app/core/security.py`, `migrations/versions/0002_identity_authentication.py` |
| Argon2id passwords | `app/core/security.py` and `tests/test_security_primitives.py` |
| Session rotation/revocation | Login creates a new session; logout and password reset revoke state; MFA verification/recovery rotate the opaque session and CSRF token without extending absolute expiry |
| Lifecycle fail-closed sessions | Login and every session lookup require an active user and, for clinic users, an active non-archived clinic; login establishes the validated clinic transaction context before forced-RLS owner/MFA role discovery |
| AUT-012 manual recovery | `password_reset_tokens` and `POST /api/v1/auth/manual-reset/consume`; no email/SMS delivery |
| AUT-013 manual invitation | `POST /api/v1/auth/manual-invite/consume` requires the one-time token, a strong password, and display name; the request schema matches the service contract |
| AUT-012 owner-issued reset | Owner-only `POST /api/v1/staff/users/{user_id}/manual-reset` creates a one-hour, single-use hashed token, returns the HTTPS setup URL once, refuses owner targets, audits issuance without the token, and deactivation consumes outstanding reset tokens; [owner-recovery.md](../runbooks/owner-recovery.md) defines the separate platform-admin/two-person production recovery procedure |
| SEC-006 CSRF | SameSite cookies, origin allowlist, and `X-CSRF-Token` validation on cookie-authenticated writes |
| MFA | TOTP secret encryption, ten hashed recovery-code records, enrollment and verification routes; successful enrollment, verification, and recovery emit redacted audit events |
| First-login MFA enrollment | `/login` consumes the explicit `mfa_enrollment_required` contract, displays the TOTP secret and one-time recovery codes once, then verifies the first authenticator code before entering the workspace; synthetic desktop/mobile coverage is in `apps/web/tests/smoke.spec.ts` |
| Auth audit | Successful login, logout, invitation consumption, password reset, and MFA actions are recorded without tokens or credential material |
| Rate limiting | Database-backed account/IP bucket with five-failure lock window |

Production follow-up: replace local defaults with provider-managed secrets and execute the PostgreSQL auth suite in CI. Owner/platform-admin recovery checks and authentication audit events are implemented in the current RBAC/governance slices.

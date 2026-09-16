# Phase 3 authentication traceability

| Requirement | Evidence |
| --- | --- |
| AUT-003 hashed sessions | `app/core/security.py`, `migrations/versions/0002_identity_authentication.py` |
| Argon2id passwords | `app/core/security.py` and `tests/test_security_primitives.py` |
| Session rotation/revocation | Login creates a new session; logout and password reset revoke state; MFA verification/recovery rotate the opaque session and CSRF token without extending absolute expiry |
| Lifecycle fail-closed sessions | Login and every session lookup require an active user and, for clinic users, an active non-archived clinic |
| AUT-012 manual recovery | `password_reset_tokens` and `POST /api/v1/auth/manual-reset/consume`; no email/SMS delivery |
| AUT-013 manual invitation | `POST /api/v1/auth/manual-invite/consume` requires the one-time token, a strong password, and display name; the request schema matches the service contract |
| SEC-006 CSRF | SameSite cookies, origin allowlist, and `X-CSRF-Token` validation on cookie-authenticated writes |
| MFA | TOTP secret encryption, ten hashed recovery-code records, enrollment and verification routes; successful enrollment, verification, and recovery emit redacted audit events |
| Auth audit | Successful login, logout, invitation consumption, password reset, and MFA actions are recorded without tokens or credential material |
| Rate limiting | Database-backed account/IP bucket with five-failure lock window |

Production follow-up: replace development defaults with provider-managed secrets, enforce owner/platform-admin role checks in the RBAC stage, add audit events, and execute the PostgreSQL auth suite in CI.

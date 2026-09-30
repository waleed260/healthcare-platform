# ADR-0007: Multi-clinic identity uses memberships plus an explicit server-side session context

- Status: Accepted — approved by human owner on 2026-09-30
- Date: 2026-09-30
- Scope: blueprint §3.1, §5.1 and §14

## Decision

Extend the current identity model from one nullable `users.clinic_id` to a global user identity with explicit clinic memberships/invitations and role/scope grants per membership. A user session has one active clinic context at a time. Context selection or switching is a server-side, CSRF-protected operation that verifies the membership, rotates the session/CSRF token, sets the transaction-local `app.clinic_id`, and records an audit event. Every request re-resolves the active context; a client-supplied clinic ID is never sufficient.

Platform-admin users remain outside ordinary clinic membership and use the existing audited support-session path for temporary clinic access. Google sign-in may identify/link the global user only after verified provider claims; it does not select or grant clinic membership. Existing single-clinic rows migrate as one membership, preserving current behavior during rollout.

### Mid-session revocation

Clinic membership validity is re-checked on every authenticated request, not only when a clinic context is first selected. If the active clinic membership is revoked or downgraded so that the current session no longer has the required access, the very next request fails authorization, clears the active clinic context, and revokes the session. The user must authenticate again and select a still-permitted context. No active session may continue operating under a revoked or insufficient membership until natural expiry or a context switch.

## Alternatives rejected

- Keep one `clinic_id` on the user: cannot represent permitted multi-clinic contexts without duplicate identities or unsafe overrides.
- Put multiple clinic IDs in a session cookie/JWT: expands the authorization surface and conflicts with transaction-local RLS context.
- Allow arbitrary context IDs from the browser: creates an IDOR risk.
- Re-check membership only at context-switch time: would let a revoked user continue working until switching contexts or session expiry, creating a security gap.

## Consequences

Authorization joins membership → role → branch/specialty scope. Session rotation and audit are mandatory on context changes. Existing login, MFA, CSRF, support, and tenant-context contracts remain the security baseline; this ADR does not authorize weakening them.

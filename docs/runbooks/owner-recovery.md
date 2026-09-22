# Owner account recovery

Owner recovery is deliberately out-of-band. The clinic owner reset endpoint
refuses owner targets; it must never be used to bypass the platform-admin
approval requirement.

For a legitimate owner recovery in production:

1. The requestor verifies the owner’s identity using the approved offline
   procedure and records only the verification reference, not identity
   documents or credentials.
2. A platform administrator records the incident, clinic, target account,
   reason, and requested action in the restricted release/support evidence
   system.
3. A different platform administrator independently reviews the evidence and
   approves the recovery. The requester and approver must be distinct people;
   one person may not satisfy both approvals.
4. The approved operator uses the controlled administrator procedure to revoke
   the owner’s active sessions and issue a one-time HTTPS reset link. The link
   is delivered manually, is shown once, and is never placed in logs, tickets,
   screenshots, or evidence bundles.
5. The operators record the approval references, issuance time, token
   destruction/consumption result, session revocation result, and audit-event
   request IDs. The token value and patient data must not be recorded.
6. The owner enrolls TOTP and confirms the recovery through a fresh session.
   The operators verify that the old sessions remain unusable and close the
   incident.

Production evidence must include both platform-admin identities, timestamps,
the offline-verification reference, approval/revocation results, and the
post-recovery smoke check. It must not contain credentials, reset tokens,
patient content, or identity documents.

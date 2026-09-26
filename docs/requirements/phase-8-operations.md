# Phase 8 operations traceability

The reception queue is now available at `/queue`. It uses the scoped queue API,
returns queue versions for optimistic commands, and provides tablet-friendly
waiting-room rows with authenticated start-consultation and complete actions,
CSRF headers, conflict errors, refresh, empty, and loading states.

| Requirement | Evidence |
| --- | --- |
| Reception queue | `queue_entries` with forced RLS, one active entry per appointment, and optimistic `version` locking |
| Queue ordering and lifecycle | `GET /api/v1/operations/queue` orders priority then check-in time; dedicated start, complete, and reorder commands enforce state/version transitions |
| Check-in transition | `POST /api/v1/operations/queue/check-in` validates version and writes two audited state transitions |
| Dashboard source | `GET /api/v1/operations/dashboard-summary` derives counts from appointment/queue/follow-up tables |
| Explicit operational reads | `GET /api/v1/operations/activity` exposes bounded, metadata-only operational audit activity; `GET /api/v1/operations/follow-ups/due-count` applies branch scope filters |
| In-app notifications/follow-ups storage | Migration creates tenant-scoped tables with forced RLS |
| Browser-push delivery | `app/modules/operations/push.py` encrypts (RFC 8291) and VAPID-signs (RFC 8292) notifications; gone subscriptions are revoked; `public/sw.js` renders them on the operations workspace |

Follow-up create/update/assign/complete commands and notification read state are implemented in `app/modules/operations/routes.py` with tenant-scoped foreign-key validation and optimistic version checks. Appointment-linked follow-ups respect branch scopes. Queue lifecycle commands use `0021_queue_commands.py`, tenant-scoped branch authorization, dedicated appointment state transitions, and audit events. Browser push subscription registration/listing/revocation encrypts credentials at rest and returns no credential material. Notification reads are restricted to the authenticated user. Overdue remains a computed state from `due_at` and clinic time rather than a mutable status, while database-backed scheduled notification jobs are owned by Phase 11. The reception critical path (waiting → start consultation → complete) is covered by an automated tablet-viewport (834×1112) Playwright test asserting versioned command payloads and CSRF headers; physical hosted tablet verification remains a release gate.
Follow-up creation now rejects archived patients and mismatched patient/appointment pairs, and follow-up reads, counts, and command lookups exclude archived patients. Queue reads and commands likewise exclude archived appointments and archived patients.
Dashboard, queue, and follow-up surfaces also exclude records attached to
inactive or archived branches, including before queue check-in and follow-up
command authorization. Follow-up creation and reassignment also require an
active, non-archived clinic staff assignee when one is supplied, and queue
check-in retains the tenant predicate on its appointment state update as a
defense-in-depth invariant alongside RLS.

The active queue collection is bounded by a signed continuation cursor, defaults
to 50 entries, caps pages at 100, and preserves deterministic priority,
check-in-time, and ID ordering while reapplying branch scope on every request.

The authenticated `/operations` workspace now gives staff a focused follow-up
and notification surface. It loads both bounded cursor collections, preserves
the API's permission scope, exposes loading/empty/error/stale states, completes
follow-ups with the returned optimistic version, and marks only the current
user's notifications read through the CSRF-protected command. Desktop/mobile
browser interaction and automated accessibility coverage are included; hosted
tablet verification remains a release gate.

Browser-push delivery is implemented in `app/modules/operations/push.py`. The
module encrypts each notification with RFC 8291 `aes128gcm` and authenticates
the request with an ES256 VAPID JWT (RFC 8292), reusing the already pinned
`cryptography` primitives rather than adding a delivery dependency. Only the
stored privacy-safe title/body/kind are sent; subscriptions whose push service
reports `404`/`410` are revoked. Delivery is opt-in through `VAPID_SUBJECT` and
`VAPID_PRIVATE_KEY`, and a partially configured identity fails closed. The
public VAPID key is exposed to the authenticated workspace through
`GET /api/v1/operations/notifications/push-config`; the browser registers
`public/sw.js`, subscribes, and stores the subscription through the existing
encrypted registration endpoint.

The follow-up collection uses the same bounded signed-cursor contract, ordered
by due time, priority, creation time, and ID; branch scope is reapplied for each
page and the computed overdue status remains server-derived.

User notifications and active browser-push subscriptions are also returned in
bounded, user-scoped cursor pages; notification payloads never include patient
content beyond the already stored privacy-safe message.

Operational activity remains metadata-only and now uses the same bounded signed
cursor contract, with stable newest-first timestamp/ID ordering.

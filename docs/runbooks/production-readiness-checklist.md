# Production readiness evidence checklist

This checklist is executed in staging with synthetic data before a pilot. It is
an evidence template, not a declaration that the release gate has passed.

## Manual WCAG 2.2 AA review

Record the deployment version, browser/assistive technology, reviewer, and UTC
timestamps. Test the public booking, login, onboarding, dashboard, schedule,
queue, patient directory/detail, and password-reset flows at desktop and tablet
widths.

| Check | Result | Evidence / defect ID |
| --- | --- | --- |
| Keyboard-only navigation reaches every control in logical order | [ ] pass [ ] fail | |
| Focus indicator remains visible and is not obscured | [ ] pass [ ] fail | |
| Screen-reader names and landmarks are understandable | [ ] pass [ ] fail | |
| Form labels, required state, errors, and success states are announced | [ ] pass [ ] fail | |
| Text, controls, focus, and status colors meet the required contrast | [ ] pass [ ] fail | |
| Reflow at 320 CSS px does not require two-dimensional scrolling | [ ] pass [ ] fail | |
| Zoom to 200% preserves task completion | [ ] pass [ ] fail | |
| Reduced-motion preference is respected where animation exists | [ ] pass [ ] fail | |
| No patient content appears in screenshots or accessibility logs | [ ] pass [ ] fail | |

Automated axe output is attached separately; every failure is either fixed or
linked to an explicitly approved defect with an owner and due date.

## Monitoring and rollback drill

Use synthetic requests and a disposable staging deployment. Do not include
credentials, patient data, request bodies, tokens, or signed URLs in evidence.

1. Confirm request count, p50/p95/p99 latency, error rate, database-pool
   saturation, job age/failures, scan backlog, backup status, and publish
   failures are visible through the platform metrics and provider dashboards.
2. Trigger a controlled 5xx alert and an authentication-rate-limit alert using
   synthetic identifiers. Record alert delivery, acknowledgement, escalation
   owner, and timestamps.
3. Deploy a reversible canary, verify health/readiness and synthetic booking,
   then roll back to the previous immutable version.
4. Confirm sessions, tenant context, background jobs, and audit events remain
   safe across the rollback. Record the deployment IDs and result links.
5. Restore the canary database backup into an isolated database and attach the
   checksum, migration head, forced-RLS count, RPO, RTO, and operator record.

| Evidence | Result | Link / owner / timestamp |
| --- | --- | --- |
| 5xx and authentication alerts | [ ] pass [ ] fail | |
| Canary health and synthetic smoke | [ ] pass [ ] fail | |
| Rollback and post-rollback smoke | [ ] pass [ ] fail | |
| Backup restore and RPO/RTO | [ ] pass [ ] fail | |
| On-call acknowledgement and escalation | [ ] pass [ ] fail | |

## Privacy, retention, and pilot approval

Attach the jurisdiction-specific retention approval, consent/privacy-request
procedure owner, incident/runbook owner, scanner and storage-provider policy
evidence, TLS/secrets configuration review, optional browser-push VAPID
credentials (see `docs/runbooks/browser-push.md`), and the pilot clinic owner’s
signed acceptance. The release evidence manifest may be marked true only after these
artifacts exist in the restricted evidence location.

| Approval | Approver | Date / evidence link |
| --- | --- | --- |
| Retention and privacy procedure | | |
| TLS, secrets, storage, and scanner review | | |
| Monitoring and rollback drill | | |
| Pilot workflow acceptance | | |

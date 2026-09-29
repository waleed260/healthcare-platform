# Dashboard data map (UX-002, OPS-005)

This map is the source of truth for dashboard content. A panel is only allowed
to show values backed by one of the endpoints below. Items marked as gaps are
intentionally omitted from the dashboard until an API exists.

| Dashboard element | Source | Status / UI decision |
| --- | --- | --- |
| Appointments KPI | `GET /api/v1/operations/dashboard-summary` → `today_appointments` | Confirmed; same scoped clinic/branch query as schedule |
| Waiting KPI | `GET /api/v1/operations/dashboard-summary` → `waiting_patients` | Confirmed; same queue scope |
| Pending approvals KPI | `GET /api/v1/operations/dashboard-summary` → `pending_approvals` | Confirmed; requested appointments |
| Follow-ups due KPI | `GET /api/v1/operations/dashboard-summary` → `followups_due` | Confirmed; active follow-up tasks |
| No-shows KPI | `GET /api/v1/operations/dashboard-summary` → `no_shows` | Confirmed |
| Today schedule table | `GET /api/v1/appointments?status=...` | Confirmed; appointment list is server-filtered by branch, doctor, and service |
| Live queue | `GET /api/v1/operations/queue` | Confirmed; `queue.manage` controls Start Consultation/Complete |
| Appointment requests | `GET /api/v1/appointments?status=requested` | Confirmed for listing; Approve/Decline actions use appointment command endpoints |
| Follow-ups due | `GET /api/v1/operations/follow-ups` | Confirmed; completion is permission-gated |
| Notification count | `GET /api/v1/operations/notifications` | Confirmed; unread count is derived from returned `read_at` values |
| Patient search | `GET /api/v1/patients?search=...` | Confirmed; search is scoped to the authenticated clinic |
| Doctor filter | `GET /api/v1/appointments?doctor_id=...` | Confirmed server-side |
| Service filter | `GET /api/v1/appointments?service_id=...` | Confirmed server-side |
| Weekly chart | No aggregate endpoint with a weekly time series | Gap; omit until a real aggregate is added |
| Trend deltas | No prior-period aggregate endpoint | Gap; omit; never fabricate deltas |

The current dashboard uses the confirmed summary and schedule sources. Queue,
operations, and patient screens use their own confirmed collection endpoints.
The optional chart and trend modules are deliberately not rendered.

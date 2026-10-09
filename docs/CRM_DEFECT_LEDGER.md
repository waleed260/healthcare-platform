# CRM Defect Ledger

Audit date: 2026-10-09

## Fixed

| # | Module | Defect | Root cause | Fix |
|---|--------|--------|------------|-----|
| 1 | Schedule | Check-in from schedule page doesn't create queue entry | Frontend called `/appointments/{id}/transitions` (status-only) instead of `/operations/queue/check-in` (atomic transition + queue entry) | Changed schedule/page.tsx line 179 to use the queue check-in endpoint |
| 2 | Schedule | Booking always fails "outside branch hours" | No `branch_hours` or `availability_rules` rows existed in the database | Seeded 7 branch_hours rows (Mon-Sat 9-18, Sun closed) and 6 availability_rules for the doctor |
| 3 | Follow-ups | JSON parse error "Unexpected token 'I', 'Internal S'..." | `response.json()` in complete/markRead had no `.catch()` — when API returned non-JSON 500, the raw SyntaxError surfaced to the user | Added `.catch()` fallback to all four `.json()` calls in operations/page.tsx |
| 4 | Follow-ups | Priority filter "Medium" returns no results | Frontend sent `priority=medium` but DB stores `priority=normal` | Changed filter option value from "medium" to "normal" |
| 5 | Analytics | Page shows empty data for all charts | Backend required `admin.analytics.read` permission (not assigned to any clinic role) while sidebar nav checks `report.read` | Changed all 4 analytics endpoints to use `report.read` |
| 6 | Reports | Branch dropdown filter has no effect | Backend `reporting-summary` didn't accept `branch_id` parameter | Added `branch_id` query param and filter clause to the appointment counts query |
| 7 | Vercel | All API calls fail with toast flood | `API_URL` env var missing on Vercel deployment | Added env var pointing to ngrok stable domain |
| 8 | Auth | Sohaib user can't log in | No user_roles assigned; then MFA enrollment record blocking login | Assigned manager role, deleted orphan mfa_methods record |

## Verified Working (no code fix needed)

| Module | Status | Notes |
|--------|--------|-------|
| Consent (Clinical) | Working | Endpoint at `/api/v1/patients/{id}/consents` via CRM router; permissions assigned |
| Prescriptions | Working | Full CRUD at `/api/v1/patients/{id}/prescriptions`; clinical.read/manage permissions assigned |
| Media upload | Working | Accepts JPEG/PNG/WebP; magic byte validation; auto-scan pipeline |
| Queue | Working | Check-in, start consultation, complete, reorder all functional |
| Dashboard | Working | KPI cards, schedule, queue, follow-ups, alerts link, weekly chart |
| Manage | Working | Services CRUD, branches, staff, roles, specialties, subscription cancel |
| Notifications | Working | List, mark-read, push subscription endpoints |
| CORS/CSRF | Working | docker-compose.yml already has both old and new Vercel URLs |

## Platform Admin

The `/admin` page correctly requires `is_platform_admin` flag (not a role permission). This is by design — platform admin features (clinic management, metrics, support access, plans, announcements) are restricted to platform operators.

## Billing & Packages

Billing module has full invoice lifecycle: create, pay, void, refund, receipt generation. Packages module supports purchase, session tracking, and utilization. Both are registered in main.py and have corresponding frontend pages. (Audited separately by background agent.)

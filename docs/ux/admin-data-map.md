# Platform admin data map

This map is the source of truth for the platform-admin surface. The panel only
renders data returned by an existing endpoint; a gap is shown as a visible
product note instead of a fabricated metric.

| Panel | Source | Status | Boundary |
| --- | --- | --- | --- |
| Clinics directory | `GET /api/v1/admin/clinics` | Confirmed | Current endpoint exposes id, name, slug, status, timezone, locale, and timestamps only. User/doctor/branch counts, storage, and onboarding are gaps. |
| Plans and limits | `GET /api/v1/admin/plans` | Confirmed | Read-only in the first panel; writes remain available through the existing governed API. |
| System health | `GET /api/v1/admin/metrics` | Confirmed | Aggregate HTTP, pool, background-job, appointment, booking, scan, storage, and publish metrics. No patient content is rendered. |
| Announcements | `GET/POST /api/v1/admin/announcements` | Confirmed | Uses the existing announcement schema and severity values. |
| Retention governance | `GET/POST /api/v1/admin/retention-policies`, approval, assignment | Confirmed | Existing governance page remains the detailed workflow. |
| Support access | `GET/POST /api/v1/admin/support-access`, revoke, plus existing activate/exit | Confirmed in this slice | Requires clinic, active requester/approver, requested permissions, reason, and 1–60 minute expiry. Platform-admin list/create/revoke emits nonclinical audit metadata; activation and expiry use the existing support context. |
| Clinic lifecycle | `POST /api/v1/admin/clinics/{clinic_id}/lifecycle` | Confirmed in this slice | Requires platform-admin MFA session, `approve`/`suspend`/`reactivate`, reason, and expected version. Suspension revokes staff sessions and booking-management tokens; all actions are audited. |
| Audit search | `GET /api/v1/admin/audit` | Confirmed in this slice | Read-only global audit events only; metadata and clinical payloads are excluded. Clinic-scoped clinical audit remains outside the platform search response. |
| Privacy requests | `GET /api/v1/admin/privacy-requests` | Confirmed in this slice | Iterates validated clinic contexts and returns workflow metadata only; patient IDs, reasons, notes, and clinical content are excluded. |
| Export requests | `GET /api/v1/admin/exports` | Confirmed in this slice | Returns workflow metadata only; patient IDs and export payloads are excluded. |

The endpoint boundary is intentional: admin pages never query patient,
appointment, or clinical-detail endpoints.

# Landing claims register

Every product statement below maps to shipped code. Synthetic numbers inside
the visual composition are labelled as previews and are not presented as
analytics.

| Claim | Shipped source | Verification |
| --- | --- | --- |
| Website builder | `apps/web/app/(authenticated)/website/page.tsx` and website API routes | Website route and website tests |
| Real availability and conflict-safe booking | appointment availability/command routes | `test_appointment_*`, booking concurrency spec |
| Shared live queue | queue page and appointment state routes | core workflow spec |
| Clinic-scoped roles and permissions | authorization service and permission-filtered shell | RBAC and authorization tests |
| Tenant-aware data access | tenant context and RLS migrations | tenant-isolation tests |
| MFA-aware protected access | identity login/MFA flow | identity policy tests |
| Audited protected actions | audit service and governance routes | audit service tests |
| Private file handling | files routes, scan status, signed access | file security tests |
| One published preview | `apps/web/app/[clinicSlug]/page.tsx` | website publishing tests |

The page does not claim pricing, customer logos, awards, compliance badges,
aggregate customer counts, or a template gallery.

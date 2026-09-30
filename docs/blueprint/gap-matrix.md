# Clinic CRM + Website SaaS blueprint reconciliation

Status: proposed for human approval before Phase 1 implementation
Sources: `Music/Clinic_CRM_Website_SaaS_Product_Blueprint.pdf` (v1.0, September 2026), `reference/pdfs/Healthcare_Platform_Codex_Implementation_Spec_v2.0.pdf`, `docs/requirements/`, and the current migrations/modules.

## Reading the status column

- **Already exists** means the current implementation or an accepted requirement provides the concept now; the evidence column names the authoritative file/table/module.
- **Extends existing concept** means the current foundation is retained and the blueprint requires additional fields, relationships, policy dimensions, or workflows.
- **Entirely new** means there is no current implementation of the named blueprint capability; the target domain is named for future planning only.

## Core entities — blueprint §3.2

| Blueprint entity | Status | Current evidence / reconciliation |
|---|---|---|
| Clinic Tenant | Already exists | `clinics` in `migrations/versions/0001_tenant_foundation.py`; subscription/governance extensions in `0012_governance.py`. Keep one isolated tenant per clinic. |
| Branch | Already exists | `branches` and branch scopes in `0003_rbac_branch_scopes.py`; lifecycle and hours in `0028_catalog_resource_lifecycle.py` and `0035_inventory_and_hours.py`. |
| Specialty | Entirely new | `doctor_profiles.specialty` is only free text in `0004_catalog_onboarding_foundation.py`, not an enabled catalog or permission dimension. Target: platform specialty registry plus clinic enablement and user/service scope; see ADR-0001. |
| Service | Extends existing concept | `services`, `doctor_services`, `branch_services` in `0004_catalog_onboarding_foundation.py`. Add specialty, commercial, treatment, booking, tax, and website fields plus master-to-clinic provenance; see ADR-0004. |
| Patient | Already exists | `patients` in `0006_appointments_engine.py`, CRM relationships in `0009_crm_foundation.py`, private files in `0010_private_files.py`. Preserve one clinic-wide patient identity and unified timeline. |
| Lead | Entirely new | No lead table/module exists. Add a tenant-scoped pipeline with source, campaign, assignment, activities, appointment linkage, and `converted_to_patient_id`; see ADR-0002. |
| Appointment | Already exists | `appointments`, exclusion constraint, history, booking tokens in `0006_appointments_engine.py` and command/state modules. Specialty linkage is a future extension; preserve the state machine and commit-time availability authority. |
| Treatment Plan | Entirely new | No treatment-plan or clinical-plan entity exists. Add plan/items/session progress and conversion links to existing appointments/services; see ADR-0005. |
| Invoice / Payment | Entirely new | Current `clinic_subscriptions` is SaaS account billing only; no patient invoices or payments. Add clinic financial documents, immutable numbering, allocations, balances, refunds/voids, and partial-payment support; see ADR-0003. |
| Website Page | Already exists | `websites`, `website_versions`, `website_pages`, `website_sections`, `website_media`, and `domain_verifications` in `0005_website_builder.py` and later publishing/versioning migrations. Dynamic CRM references and broader section/block coverage extend it. |

## Capabilities — blueprint §§4–24

| Blueprint section / capability | Status | Evidence / target reconciliation |
|---|---|---|
| 4.1 Super Admin dashboard: clients | Extends existing concept | Platform-admin context, clinic lifecycle routes, and admin UI exist in `0036_platform_admin_context.py`, `app/modules/governance/admin_routes.py`, and `apps/web/app/admin/`; add client-health metrics. |
| 4.1 revenue, renewals, usage, support metrics | Extends existing concept | Plans, subscriptions, feature usage, audit, and support sessions exist in `0012_governance.py`, `0018_feature_usage.py`, `0044_support_context_sessions.py`; financial/renewal/health aggregation is new reporting work. |
| 4.2 clinic account lifecycle | Already exists | Governance service/routes and `clinic_subscriptions` support lifecycle, plan assignment, limits, and status; blueprint adds commercial fields, account owners, notices, and richer health. |
| 4.2 specialty enable/disable | Extends existing concept | Existing plan/subscription and platform-admin controls are the extension point; specialty enablement is new and governed by ADR-0001. |
| 4.2 support/impersonation | Already exists | Audited temporary support sessions in `support_access_sessions`, `0044_support_context_sessions.py`, and governance routes. Do not redesign. |
| 4.3 locked-module upgrade request workflow | Entirely new | No clinic upgrade-request entity or end-to-end workflow exists; extend governance with request, review, decision, and audit records. |
| 4.4 plan builder: specialty/branch/staff limits | Extends existing concept | `plans`, `feature_limits`, `clinic_subscriptions` in `0012_governance.py`; specialty-lock semantics and editable plan builder are ADR-0006. |
| 4.4 website/reports/storage/packages/branding/support flags | Extends existing concept | Existing feature limits and usage counters are the control plane; package/inventory/branding capabilities are not all implemented and must be represented as feature codes, not bespoke plan columns. |
| 5.1 email/password authentication | Already exists | `users`, sessions, password policy and auth service in `0002_identity_authentication.py` and `app/modules/identity/service.py`. |
| 5.1 Google sign-in | Entirely new | No external identity-provider credential/link flow exists. Add only after the context model in ADR-0007 is approved. |
| 5.1 Microsoft sign-in later | Entirely new | Explicitly future integration; no Phase 1 dependency. |
| 5.1 reset, recovery, sessions, MFA readiness | Already exists | Password reset, opaque sessions, CSRF, MFA/TOTP and recovery codes in `0002_identity_authentication.py`, `app/core/security.py`, and phase-3 traceability. |
| 5.1 invite-based onboarding | Already exists | `staff_invitations`, onboarding checklist, and staff routes in `0002_identity_authentication.py`, `0025_staff_invitation_rls.py`, and catalog onboarding. |
| 5.1 guided first-login setup | Extends existing concept | `0029_clinic_onboarding.py` and `/onboarding` exist; specialty, currency, service selection, and branding steps need blueprint alignment. |
| 5.2 client navigation / module visibility | Extends existing concept | Authenticated web shell, permissions, feature limits, and module routes exist; specialty and plan gates must be added without client-only authorization. |
| 6.1 specialty library | Entirely new | No platform specialty registry or clinic-specialty join exists. Dental, Hair, Skin, Dermatology, and future keys are data/configuration targets under ADR-0001. |
| 6.2 unified and specialty views | Extends existing concept | Unified clinic/branch/patient model exists; add specialty filters, joins, reporting dimensions, and user specialty scopes. |
| 7.1 master service catalog | Entirely new | Current services are clinic-owned rows only. Add platform-owned templates and clinic selection/copy provenance; ADR-0004 commits to editable copies. |
| 7.1 clinic catalog and custom services | Already exists / extends | Clinic `services` and CRUD are in catalog module; add master-copy source and complete blueprint fields. |
| 7.2 service commercial/scheduling/treatment/website fields | Extends existing concept | Existing service has core duration/active/description data; add price currency tax discount deposit, buffers, sessions, follow-up, custom fields, visibility, and slug. |
| 7.3 specialty-specific custom fields | Entirely new | No configurable field-definition/value framework exists; build after specialty model, with schema-safe typed values and scoped visibility. |
| 8 package definition and purchase | Entirely new | No package domain or patient financial purchase records exist. |
| 8 session consumption/progress/overuse override | Entirely new | Appointment table is the existing visit record; ADR-0005 chooses a treatment-plan-session ledger rather than overloading appointment status. |
| 9.1 lead capture/pipeline/source/ownership/activity | Entirely new | No lead tables/routes/UI. Future lead domain must accept website/manual/import sources and audit assignment/status transitions. |
| 9.1 lead-to-appointment linkage | Extends existing concept | Existing appointments support patient/service/branch/provider; add nullable lead linkage while keeping public booking integrity. |
| 9.1 conversion without duplication | Entirely new | Implement lead conversion transaction with `converted_to_patient_id`, dedupe review, and no second patient profile; ADR-0002. |
| 9.2 patient profile medical/communication/clinical/financial summary | Extends existing concept | Core patient, contacts, notes, consent, files, media/audit foundations exist; treatment, billing, package, and specialty data are future extensions. |
| 9.3 unified patient timeline | Extends existing concept | Appointment history and CRM history endpoints exist; add treatment, financial, lead-conversion, media, and follow-up event types with privacy filtering. |
| 10 calendar views and appointment CRUD | Already exists | Appointment routes, scheduling, availability, cursor reads, and responsive schedule surface exist. Preserve contracts. |
| 10 provider hours/leave/blocked time/buffers | Already exists | `branch_hours`, holidays, leave/resource blocks, availability engine, and catalog assignments exist in migrations and scheduling modules. |
| 10 source/lead linkage and recall | Extends existing concept | Appointment source/questions and follow-ups exist; lead linkage and recall-specific workflow are new extensions. |
| 10 check-in/live queue | Already exists | Queue tables/commands and tablet workflow in operations module and `0007`–`0008`, `0021`; no redesign. |
| 11 treatment plans/items/progress | Entirely new | No treatment plan entity; ADR-0005. |
| 11 notes/prescriptions/consent/media/documents | Extends existing concept | Notes/consent/files/media safety and audit exist; prescriptions and specialty forms are new clinical extensions. |
| 11 explicit approved-for-website media | Already exists / extends | Website media scanning, immutable publishing, and public-media safeguards exist in `0031`–`0033` and website publishing; add patient consent/approval linkage. |
| 12 invoice workflow and taxes/discounts | Entirely new | No patient billing domain; ADR-0003. |
| 12 full/partial payments and balances | Entirely new | No payment ledger; ADR-0003 commits to allocations and partial payments from the first billing schema. |
| 12 invoice/receipt outputs and numbering | Entirely new | No document renderer/number sequence for patient billing; numbering must be clinic-scoped and concurrency-safe under ADR-0003. |
| 12 financial states, aging, cashier/provider revenue | Entirely new | New financial reporting/read models; SaaS subscription status remains a separate domain. |
| 13 inventory/products/stock/alerts | Extends existing concept | `0035_inventory_and_hours.py` and catalog resources provide the foundation; complete product stock ledger, branch inventory, thresholds, and audited adjustments. |
| 13 operational/financial/lead/treatment reports | Extends existing concept | Dashboard summary, feature usage, audit and appointment/CRM queries exist; add new domain aggregates after source entities are approved. |
| 14 role examples and permission catalog | Extends existing concept | Roles/permissions and branch scopes in `0003`, `0017`, authorization module; add accountant/consultant/custom role presets only where needed. |
| 14 module/action permissions | Already exists / extends | Permission catalog and route guards exist; add billing, lead, treatment, inventory, specialty and media actions. |
| 14 specialty-level permission | Entirely new | No specialty scope exists; implemented only through ADR-0001’s shared tenant + branch + specialty predicate model. |
| 14 branch-level permission | Already exists | `user_branch_scopes`, SQL reapplication, and branch-aware authorization are implemented. |
| 14 sensitivity/security baseline | Already exists / extends | RLS, CSRF, MFA, rate limiting, encrypted fields, scans, audit, backup runbooks and governance are present; blueprint clinical/financial actions add permission coverage. |
| 15 editor layout and page management | Extends existing concept | Structured website pages/sections/editor and publishing exist; expand section library and editor controls. |
| 15 section/block library | Extends existing concept | Current allowed section types are controlled and safe; add blocks/categories without unrestricted HTML/JS. |
| 16 theme/header/footer/responsive editing | Extends existing concept | Website templates, sections, CSS/design tokens, and responsive surfaces exist; global theme/header/footer model is incomplete. |
| 17 dynamic service/provider/branch/appointment integration | Extends existing concept | Website and catalog records already share tenant scope; add safe dynamic references/snapshots and specialty filters. |
| 17 patient media integration | Extends existing concept | Existing public-media controls are strong; explicitly connect approved patient assets only. |
| 18 domains/publishing/version history | Already exists | Domain verification, draft/live versions, publish, rollback and preview-token controls exist in website migrations/service. |
| 18 SEO/performance/integrations | Extends existing concept | Basic website safety and publishing exist; broaden SEO metadata, asset optimization and plan-gated analytics/custom code later. |
| 19 media library/forms/templates/blog | Extends existing concept | Media upload/scanning and controlled website sections exist; form-to-lead/appointment, folders, blog and specialty templates are future work. |
| 20 client dashboard/quick actions | Extends existing concept | Dashboard shell, operations summary, queue and CRM screens exist; add lead, billing, package and specialty metrics/actions. |
| 21 notifications/internal tasks | Extends existing concept | Follow-ups, notifications, browser push and scheduled jobs exist; add billing/package/upgrade/stock event producers. |
| 22 onboarding workflow | Extends existing concept | Platform clinic creation, onboarding checklist, staff/catalog/website foundations exist; connect specialty, lead, billing and website paths. |
| 22 lead-to-patient workflow | Entirely new | Depends on ADR-0002 plus treatment and billing decisions; appointments/queue/CRM endpoints are existing steps. |
| 22 multi-specialty expansion workflow | Entirely new | Requires specialty join, upgrade request, scope predicates, catalog templates and website/report activation. |
| 23 SaaS billing/account health | Extends existing concept | `plans`, `feature_limits`, `clinic_subscriptions`, usage and admin health primitives exist; revenue/renewal/commercial account health is incomplete. |
| 24 performance/pagination | Already exists / extends | Cursor-bounded collections, indexes, load-profile tooling and website media limits exist; new entities must follow the same contract. |
| 24 reliability/autosave/transactions/backups | Already exists / extends | Website drafts, transactional booking/governance actions, backup/restore runbooks exist; billing must be transactional and idempotent. |
| 24 scalability/tenant-aware modularity | Already exists / extends | FastAPI modular monolith, PostgreSQL RLS/composite FKs, feature limits and migrations establish the pattern; specialty is an added dimension. |
| 24 accessibility/responsive UX | Extends existing concept | Playwright/axe coverage and responsive screens exist; future surfaces inherit the same release gates. |
| 24 observability/data portability | Already exists / extends | Request IDs, audit, jobs, health/readiness, privacy exports and governance exist; add new domain events/exports with sensitivity controls. |

## Explicitly unchanged systems

The following are carried forward as constraints, not redesigned by the blueprint reconciliation: the appointment lifecycle/state machine and exclusion-based booking authority; transaction-local tenant context and forced-RLS/composite-FK isolation; CSRF/session/MFA/password-recovery controls; branch scope enforcement; append-only audit events and governed support sessions; private file/media scanning and explicit public publishing gates; website draft/live version topology; cursor pagination and API error/response conventions; platform admin separation; backup/restore and release gates. Future extensions must call these contracts rather than bypass them.

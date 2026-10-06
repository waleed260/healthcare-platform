# CRM Implementation Plan v3

> Source: [Artifact](https://claude.ai/artifact/ErPxcFppjwCLKSFRfxCxKa) · Generated October 6, 2026
> 16 phases · ~100 tasks · 18 weeks · 2 parallel developers

## Codebase Baseline

- 20 API modules (~750 lines each, real CRUD)
- 108 DB tables with RLS on every tenant table
- 71 API test files + 9 Playwright E2E specs
- Schema: raw SQL (no alembic version files — stamp only)
- Frontend: 18 pages, most thin list views (15–150 lines)
- Website editor: 849 lines, 30+ section types in library
- `theme.py`: full Pydantic models (ThemeSettings, HeaderSettings, FooterSettings, DeviceOverrides, SeoSettings)
- `publishing.py`: immutable JSON snapshots with checksums

## Staffing

Two parallel tracks:
- **CRM track** (Dev A): P3 → P4 → P5 → P6 → P12 → P13
- **Website track** (Dev B): P7 → P8 → P9 → P10 → P11
- **Shared sequential**: P1, P2, P14, P15, P16

---

## Phase 1 — Fix confirmed defects (Week 1, ~4 days)

Priority: **Immediate** | Depends on: Nothing

### Website editor & preview
- **1.1** Fix preview URL `token=undefined` — `draft_version_id` is null when no snapshot saved yet; call `refresh_draft_snapshot()` before generating preview token (4h) [FIX]
- **1.2** Fix `/book/preview` "Clinic not found" — booking page uses hostname lookup; preview needs clinic_slug context via query param (3h) [FIX]
- **1.3** Fix section save "request could not be validated" — new section returns `version: 1` but editor sends `version: 0` on first edit; sync initial version (2h) [FIX]
- **1.4** Fix mobile preview clipping — current device toggle changes CSS class only; use real iframe width or `transform: scale()` with container (4h) [FIX]

### Dashboard & navigation
- **1.5** Fix "Today = 0" with stale appointments — `dashboard-summary` query uses UTC midnight; use clinic branch timezone from `branches.timezone` (3h) [FIX]
- **1.6** Fix account menu — avatar button has no click handler; add dropdown: name, email, role, Security link, Sign out (3h) [FIX]
- **1.7** Consolidate duplicate website color settings — `brand.primary_color` (flat) vs `brand.theme.colors.primary` (nested) both exist; migrate flat → nested, single source in editor (4h) [FIX]

### Already shipped
- **1.8** Session idle refresh `db.commit()` in 6 GET endpoints [DONE]
- **1.9** Frontend 401 → /login redirect in all pages [DONE]
- **1.10** CSRF duplicate cookie fix + freshCsrf() for MFA [DONE]

**Files:** `apps/api/app/modules/operations/routes.py` · `apps/api/app/modules/websites/routes.py` · `apps/web/app/(authenticated)/workspace-shell.tsx` · `apps/web/app/(authenticated)/website/page.tsx`

---

## Phase 2 — UI foundations (Week 2, ~5 days)

Priority: **High** | Depends on: P1

### Core components
- **2.1** Reusable drawer/modal: slide-over panel with form state, close confirmation on dirty, escape key, focus trap (6h) [NEW]
- **2.2** Grouped navigation: collapsible groups (Home, CRM, Clinical, Business, Website, Management). Responsive sidebar/drawer (6h) [ENHANCE]
- **2.3** Pagination component: cursor-based for API lists, page size selector, result count (3h) [NEW]
- **2.4** Toast/notification system: success/error/info toasts replacing scattered alert states (2h) [NEW]
- **2.5** Confirmation dialog: "Are you sure?" for consequential actions (2h) [NEW]

### Quick action forms (wired to existing API endpoints)
- **2.6** Add Patient drawer → `POST /api/v1/patients` with duplicate detection (4h) [NEW]
- **2.7** Add Appointment drawer → `POST /api/v1/appointments` with conflict validation (5h) [NEW]
- **2.8** Block Time drawer → `POST /api/v1/scheduling/blocked-slots` (2h) [NEW]
- **2.9** Create Follow-up drawer → `POST /api/v1/follow-ups` (2h) [NEW]

**New files:** `apps/web/app/(authenticated)/_lib/drawer.tsx`, `_lib/pagination.tsx`, `_lib/toast.tsx`, `_lib/confirm.tsx`

---

## Phase 3 — CRM: patients & leads (Weeks 3–4, ~9 days)

Priority: **High** | Depends on: P2 (drawer, pagination)

### Patients (current: 46-line list + 140-line detail)
- **3.1** Expand patient list: search, status filter, pagination (4h) [ENHANCE]
- **3.2** Unified patient timeline: merge all event types chronologically via `GET /patients/{id}/history` (8h) [ENHANCE]
- **3.3** Patient detail tabs: Overview, Timeline, Appointments, Treatments, Notes, Prescriptions, Documents/Consent, Media, Invoices/Payments, Packages (12h) [ENHANCE]
- **3.4** Duplicate detection + merge: `POST /patients/duplicate-candidates`, `POST /patients/{id}/merge` (4h) [NEW]

### Leads (current: 89-line list only)
- **3.5** Lead pipeline/kanban: stages (New → Contacted → Qualified → Booked → Visited → Converted/Lost). Drag or dropdown (10h) [NEW]
- **3.6** Lead creation form: contact, source, campaign, service, specialty, branch, owner (4h) [NEW]
- **3.7** Lead detail page: activity timeline, stage history, follow-up scheduling, convert-to-patient (8h) [NEW]
- **3.8** Lead → Patient conversion: link records, preserve attribution, prevent double conversion (4h) [NEW]

---

## Phase 4 — Schedule, queue & tasks (Weeks 3–4, parallel with P3, ~10 days)

Priority: **High** | Depends on: P2 (drawer)

### Calendar (current: 46-line list)
- **4.1** Day view: time column, provider columns, appointment blocks, click-to-add (10h) [NEW]
- **4.2** Week view: 7-day grid. Month view: day cells with count + overflow (8h) [NEW]
- **4.3** Filter bar: provider, branch, specialty. Show blocked/leave slots greyed (4h) [NEW]
- **4.4** Appointment detail drawer: full status lifecycle, reschedule, cancel with reason (6h) [NEW]

### Queue (current: 21-line stub)
- **4.5** Live queue board: patient, time, service, provider, wait duration, status, actions. Auto-refresh 30s (8h) [NEW]
- **4.6** Queue check-in from schedule + reorder (3h) [ENHANCE]

### Follow-ups & tasks
- **4.7** Task list with filters: due date, assignee, priority, patient/lead link, status (4h) [ENHANCE]

---

## Phase 5 — Billing & finance (Week 5, ~6 days)

Priority: **High** | Depends on: P3 (patient records)

### Invoices
- **5.1** Invoice builder: line items, qty, price, discount, tax, live totals (10h) [ENHANCE]
- **5.2** Invoice from appointment/treatment: prefill, snapshot prices (4h) [NEW]
- **5.3** Payment recording: method, amount, reference, full + partial (5h) [ENHANCE]
- **5.4** Refund/void: permission-gated, reason required, audit record (4h) [NEW]

### Finance
- **5.5** Daily cashier: date picker, method totals, invoiced vs collected (4h) [ENHANCE]
- **5.6** Expense management: list, create, void (3h) [ENHANCE]
- **5.7** Provider commissions: revenue table + rules (3h) [ENHANCE]

---

## Phase 6 — Clinical & specialty tools (Weeks 6–7, ~10 days)

Priority: **Medium-High** | Depends on: P3 (patient records)

### Treatment plans
- **6.1** Plan list + create form (6h) [ENHANCE]
- **6.2** Plan item lifecycle: recommended → completed/cancelled (5h) [ENHANCE]
- **6.3** Prescriptions UI: medication, dose, frequency, print (5h) [NEW]

### Specialty tools (APIs exist)
- **6.4** Dental: interactive SVG tooth chart (12h) [NEW]
- **6.5** Hair: Norwood scale, graft plan (6h) [NEW]
- **6.6** Skin: body area selector, session log (6h) [NEW]

### Forms & consent
- **6.7** Clinical forms builder (8h) [ENHANCE]
- **6.8** Consent management with signature capture (5h) [NEW]

---

## Phase 7 — Website: theme system (Weeks 5–7, ~15 days)

Priority: **High** | Depends on: P1 (editor fixes)

### Database migration
- **7.1** Create `theme_instances` table (3h) [MIGRATE]
- **7.2** Add `theme_instance_id` FK to pages/sections, backfill (3h) [MIGRATE]
- **7.3** RLS policy + section type constraint update (2h) [MIGRATE]

### Backend API
- **7.4** Theme instance CRUD + draft limit enforcement (6h) [NEW]
- **7.5** Publish theme: validate → snapshot → swap → demote (5h) [ENHANCE]
- **7.6** Update `build_draft_snapshot()` for theme scoping (4h) [ENHANCE]

### Frontend: themes landing
- **7.7** Themes landing page: live + draft cards (8h) [NEW]
- **7.8** Theme actions: Duplicate, Rename, Preview, Publish, Archive (5h) [NEW]

### Clinic Starter theme
- **7.9** Compose 15+ default pages (12h) [NEW]
- **7.10** Theme brand defaults: palette, typography, header/footer (4h) [NEW]
- **7.11** Starter content authoring (6h) [NEW]
- **7.12** Install flow: seed pages + sections + brand (4h) [NEW]

---

## Phase 8 — Website: editor enhancements (Weeks 7–9, ~12 days)

Priority: **High** | Depends on: P7

### Right panel settings
- **8.1** Content tab: rich text + block selector (8h) [ENHANCE]
- **8.2** Design tab: background, overlay, border/shadow (8h) [NEW]
- **8.3** Layout tab: width, padding, alignment, columns (8h) [NEW]
- **8.4** Responsive tab: device overrides (6h) [NEW]

### Editor infrastructure
- **8.5** Device preview: real viewport widths + scale (5h) [ENHANCE]
- **8.6** Undo/redo: command stack, Ctrl+Z/Shift+Z (8h) [NEW]
- **8.7** Autosave: debounce 3s, save indicator (5h) [ENHANCE]
- **8.8** Version history panel (4h) [ENHANCE]

### Global theme settings
- **8.9** ThemeSettings UI: colors, typography, buttons, layout, forms (8h) [ENHANCE]
- **8.10** Header settings UI (6h) [ENHANCE]
- **8.11** Footer settings UI (4h) [ENHANCE]

---

## Phase 9 — Website: public renderer & CRM binding (Weeks 8–9, ~13 days)

Priority: **High** | Depends on: P8

### Public renderer expansion
- **9.1** Split SectionBlock into per-type components (6h) [ENHANCE]
- **9.2** Hero variants: split, full-image, video, doctor, booking (8h) [ENHANCE]
- **9.3** Services: cards, grid, slider, spotlight, pricing (8h) [ENHANCE]
- **9.4** Content sections: FAQ, timeline, comparison, gallery, video (10h) [NEW]
- **9.5** Contact/location: branch data binding (4h) [ENHANCE]
- **9.6** Universal section settings: CSS variable injection (6h) [NEW]

### CRM data binding
- **9.7** Dynamic/Manual data mode for sections (6h) [FIX]
- **9.8** Doctor data binding from real records (3h) [FIX]
- **9.9** Testimonial/results: approved + consented only (4h) [ENHANCE]

### Booking page
- **9.10** Multi-step booking UX (8h) [ENHANCE]
- **9.11** Real availability integration (4h) [ENHANCE]
- **9.12** Booking confirmation + reference (3h) [ENHANCE]

### Preview & publish
- **9.13** Fix preview tokens (3h) [FIX]
- **9.14** Publish validation: legal pages, contrast check (4h) [ENHANCE]

---

## Phase 10 — Website: domains, media & SEO (Week 10, ~6 days)

Priority: **Medium** | Depends on: P9

- **10.1** Domains page: list, DNS/cert status (6h) [NEW]
- **10.2** Add domain flow: validate, TXT proof, verify (6h) [ENHANCE]
- **10.3** Primary domain: canonical URLs, sitemap, redirects (4h) [NEW]
- **10.4** Media library UI: upload, alt text, search (6h) [ENHANCE]
- **10.5** Per-page SEO: title, description, OG image (4h) [ENHANCE]
- **10.6** Custom CSS editor per-theme/section (6h) [NEW]

---

## Phase 11 — Content: blog, forms & testimonials (Week 11, ~5 days)

Priority: **Medium-High** | Depends on: P9, P10

### Blog
- **11.1** Post editor: title, slug, rich text, category/tags, scheduling (8h) [NEW]
- **11.2** Post list: filter, search, bulk actions (3h) [ENHANCE]
- **11.3** Per-post SEO (2h) [ENHANCE]
- **11.4** Blog public rendering: listing + detail (6h) [NEW]

### Form builder
- **11.5** Form editor: drag fields, types, validation, routing (6h) [NEW]
- **11.6** Submission handling: success message, lead creation, export (4h) [NEW]

### Testimonial moderation
- **11.7** Moderation workflow: pending → approved → rejected (3h) [ENHANCE]
- **11.8** Display settings: selection, rating, name display (2h) [ENHANCE]

---

## Phase 12 — Management: services, staff, specialties (Weeks 11–12, ~6 days)

Priority: **Medium** | Depends on: P2

- **12.1** Service creation: from catalog or custom (8h) [ENHANCE]
- **12.2** Service edit/detail: all fields, deactivate, duplicate (4h) [ENHANCE]
- **12.3** Staff invitation + pending list (5h) [ENHANCE]
- **12.4** Role editor: permissions, branch scope (6h) [NEW]
- **12.5** Specialty/Plan tab: limits, usage, upgrade request (4h) [ENHANCE]

---

## Phase 13 — Packages, inventory & reports (Week 13, ~6 days)

Priority: **Medium** | Depends on: P5

- **13.1** Package catalog: create, services, pricing (5h) [NEW]
- **13.2** Patient package tracking: purchase, consume sessions (5h) [NEW]
- **13.3** Inventory: products, stock adjustments, low-stock alerts (6h) [ENHANCE]
- **13.4** Report dashboard: charts, filters, date range (10h) [NEW]
- **13.5** Export: CSV/PDF, role-gated (3h) [ENHANCE]

---

## Phase 14 — Platform admin & security (Weeks 14–15, ~8 days)

Priority: **Medium** | Depends on: P12

- **14.1** Expand admin: tenant list, usage, metrics (8h) [ENHANCE]
- **14.2** Tenant onboarding: create clinic → plan → invite (8h) [NEW]
- **14.3** Subscription management (4h) [ENHANCE]
- **14.4** Security page rewrite: real MFA state, sessions, recovery (5h) [ENHANCE]
- **14.5** Privacy page fix + data export/deletion (4h) [FIX]
- **14.6** Audit log viewer (4h) [ENHANCE]

---

## Phase 15 — Testing, hardening & validation (Weeks 16–18, ~15 days incl 5-day buffer)

Priority: **Critical** | Depends on: All phases

- **15.1** Two-tenant isolation test (8h) [ENHANCE]
- **15.2** Multi-role permissions test (6h) [ENHANCE]
- **15.3** Theme isolation test (4h) [NEW]
- **15.4** Responsive validation: screenshots at all widths (6h) [NEW]
- **15.5** CRM binding test (3h) [NEW]
- **15.6** Preview token validation (3h) [NEW]
- **15.7** Full CRM workflow acceptance (6h) [NEW]
- **15.8** Billing validation (4h) [NEW]
- **15.9** Timezone reconciliation (3h) [NEW]
- **15.10** 5-day risk buffer [FIX]
- **15.11** Blog flow acceptance (2h) [NEW]
- **15.12** Form flow acceptance (2h) [NEW]
- **15.13** Booking page acceptance (2h) [NEW]

---

## Migration Plan

No alembic version files (stamp only). All migrations are raw SQL against Docker postgres.

### Phase 7 — theme instances (only structural migration)
- **M1** `CREATE TABLE theme_instances` with RLS
- **M2** `ALTER TABLE website_pages ADD COLUMN theme_instance_id uuid`
- **M3** Backfill: create "Live" theme instance per website
- **M4** Drop `section_type_check` constraint (expand to 30+ types)

### No-migration changes
- **M5** Section design/layout → existing `content` jsonb [DONE]
- **M6** Theme/header/footer/SEO → existing `brand` jsonb [DONE]

**Rollback:** M1–M3 additive (drop column + table). M4 re-add constraint with expanded list.

---

## Risk Register

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Single developer | High | Medium | Timeline → ~28 weeks. Decide track priority at kickoff |
| Theme isolation breaks existing | High | Medium | Backfill creates matching "Live" instance. Feature-flag. Test on healthcare_test first |
| Renderer scope creep (30+ sections) | Medium | High | Prioritize 10 most-used types. Remaining as generic card grids |
| Calendar complexity | Medium | Medium | Day view first, week/month progressive |
| Docker rebuild cycle | Low | High | Batch API changes. Volume mount for dev |
| Timezone bugs | High | Medium | Timezone-aware fixtures. Cross-TZ reconciliation test |
| Vercel deployment lag | Low | Medium | PR-based deploys. Preview URLs before merge |

---

## Timeline

| Week | Track A (CRM) | Track B (Website) |
|------|--------------|-------------------|
| 1 | P1 Defects (shared) | P1 Defects (shared) |
| 2 | P2 UI Foundations (shared) | P2 UI Foundations (shared) |
| 3–4 | P3 CRM (9d) | P4 Schedule (10d) |
| 5–6 | P5 Billing (6d) | P7 Themes + Starter (15d) |
| 6–8 | P6 Clinical (10d) | P8 Editor (12d) |
| 9–10 | — | P9 Renderer + Booking (13d) |
| 11 | — | P10 Domains/SEO + P11 Content |
| 12 | P12 Management (6d) | — |
| 13 | P13 Pkgs/Reports (6d) | — |
| 14–15 | P14 Platform Admin (8d) | — |
| 16–18 | P15 Testing + Hardening + Buffer (shared) |

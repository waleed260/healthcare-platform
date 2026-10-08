# Pre-Launch Checklist

## Infrastructure
- [ ] PostgreSQL backups configured (daily snapshots, 30-day retention)
- [ ] Supabase RLS policies verified on all tables (run `SELECT tablename FROM pg_tables WHERE schemaname='public'` and confirm each has tenant isolation)
- [ ] Alembic migrations applied to production (`alembic upgrade head` — currently 0001–0022)
- [ ] `healthcare_runtime` role has correct GRANT permissions
- [ ] Environment variables set: `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `JWT_SECRET`, `ALLOWED_ORIGINS`
- [ ] CORS `ALLOWED_ORIGINS` locked to production domains only (no wildcard)

## API
- [ ] Rate limiting enabled on public endpoints (`/public/sites`, `/public/catalog`, lead submission)
- [ ] Idempotency-Key header enforced on all mutating public endpoints
- [ ] Health check endpoint (`/api/v1/health`) returns 200
- [ ] All CRUD routes require valid JWT with correct permissions
- [ ] Optimistic versioning (`expected_version`) active on all mutation endpoints
- [ ] File upload size limits configured (media picker, result photos)

## Frontend
- [ ] `next build` succeeds with zero errors
- [ ] Vercel `API_URL` environment variable points to production API
- [ ] Public site renders correctly for all 3 templates (calm_clinic, editorial_practice, warm_studio)
- [ ] Booking flow works end-to-end (service → provider → slot → confirm)
- [ ] Lead form submission works and creates lead in CRM
- [ ] SEO meta tags render (title, description, OG tags, canonical, robots)
- [ ] 404 page renders for missing clinics and missing pages
- [ ] Draft preview with `?preview_token=` works
- [ ] Redirects configured in website builder execute correctly

## Website Builder
- [ ] 3-panel editor loads (page list, canvas, settings)
- [ ] All 24 section types can be added and rendered
- [ ] Drag-and-drop reorder persists section positions
- [ ] Theme brand editor saves colors, fonts, header/footer settings
- [ ] Theme instances: create draft, activate (promote to live), archive
- [ ] Publish flow: validate → build snapshot → deploy
- [ ] Starter pages seeded on new website creation (6 pages)
- [ ] Custom CSS per section applies in preview and published site
- [ ] Device-responsive hide rules (tablet/mobile) work

## CRM
- [ ] Patient list loads with search, filters, pagination
- [ ] Lead capture → patient conversion flow works
- [ ] Appointment scheduling with slot availability
- [ ] Queue management: check-in, reorder, call-next
- [ ] Notifications: created on events, dismissible, real-time badge count
- [ ] Forms: drag-and-drop builder, public embed, submission storage

## Auth & Security
- [ ] Login/signup flow with email verification
- [ ] Role-based permissions enforced (admin, staff, viewer)
- [ ] Clinic-scoped RLS prevents cross-tenant data access
- [ ] Password reset flow works
- [ ] Session expiry and refresh token rotation
- [ ] No secrets in client-side code or git history

## Domain & DNS
- [ ] Custom domain configuration works (add domain → verify DNS → SSL)
- [ ] Default subdomain routing (`{slug}.carefully.health` or equivalent)
- [ ] SSL certificates auto-provisioned

## Monitoring
- [ ] Error tracking configured (Sentry or equivalent)
- [ ] API request logging with `request_id` correlation
- [ ] Database connection pool monitoring
- [ ] Uptime monitoring on health endpoint

## Data
- [ ] Sample clinic data can be created via onboarding
- [ ] Data export capability confirmed (GDPR/compliance)
- [ ] Soft-delete (`archived_at`) working on all major entities
- [ ] Audit trail: `created_at`, `updated_at` timestamps on all tables

# Full-Project Review — Gaps, Errors & Missing Pieces

- **Date:** 2026-10-04
- **Branch reviewed:** `feat/premium-ui-animations` @ `1b2198f`
- **Method:** live verification (typecheck, lint, production build, full backend test suite against a freshly migrated PostgreSQL, contract drift check, config/docker/CI/docs audit) plus a manual read of every top-level area of the repo. Every finding below was reproduced or directly observed — nothing is speculative unless marked as such.

---

## 1. Verified-healthy baseline (what passed)

| Check | Result |
|---|---|
| `tsc --noEmit` (web) | ✅ clean |
| `eslint .` (web) | ✅ 0 errors (3 known `<img>` warnings) |
| `next build` | ✅ succeeds, 33 routes |
| Backend tests on a **freshly migrated** DB | ✅ **262 passed, 2 skipped** (skips are config-gated storage tests) |
| OpenAPI / TS contract drift | ✅ none (`packages/contracts` matches code) |
| Production config validation (`core/config.py`) | ✅ fails closed on secrets/HTTPS/storage/forwarded-IP |
| Secret hygiene | ✅ `.env`, `.env.save`, `docker.env`, `.vercel`, `*.tsbuildinfo` all untracked |

The test failure you will see if you run the suite against the **currently running local stack** is explained by finding #1 — it is an environment problem, not a code bug.

---

## 2. Critical

### 2.1 Migration renumbering has stranded deployed databases ⚠️ *highest-impact finding*
- The running local DB is at revision **`0055_lead_activities`**, but in the current tree that migration is **`0057_lead_activities`** — 11 migrations (0055–0066) were renumbered/inserted into the middle of the history.
- Consequence: `alembic upgrade head` on any DB that applied the old numbering now fails:
  `ERROR Can't locate revision identified by '0055_lead_activities'`.
- The live local stack (up 23h, healthy) is serving API traffic against a schema that is 11 migrations old, and its `migrate` service cannot self-heal.
- This violates the append-only rule the project's own governance depends on. CI's `downgrade -1` / offline-SQL checks cannot catch renames of *already shipped* migrations.
- **Fix:** stamp the stranded DBs to the equivalent new revision (verify schema first), then add a policy/check that shipped migration filenames are immutable (e.g., a CI test that fails if a revision name changes after it appears on `main`).

### 2.2 No way to log out of the product UI
- The backend exposes `POST /api/v1/auth/logout` (`identity/routes.py:88`), but **no frontend element calls it**. The only sign-out affordances are on `/security` and they can revoke *other* devices only.
- The avatar button in `workspace-shell.tsx` is labeled `aria-label="Open account menu"` but has **no onClick handler** — a dead control where a menu (with logout) would naturally live.
- For a healthcare product routinely used on shared reception machines, session termination is not optional. **Fix:** wire the avatar to a menu containing "Sign out" → `POST /auth/logout`.

### 2.3 No error / not-found / loading boundaries anywhere in the app
- `find apps/web/app -name "error.tsx" -o -name "not-found.tsx" -o -name "loading.tsx" -o -name "global-error.tsx"` returns **nothing**.
- Every page fetches from the API server-side; when the API is down or slow, public clinic sites (`/[clinicSlug]`) and all workspace pages render Next's **default unbranded error screen** (and default 404s for bad slugs).
- **Fix:** add at minimum `app/error.tsx`, `app/not-found.tsx`, and a boundary under `(authenticated)`; clinic public sites deserve their own branded boundary.

---

## 3. High

### 3.1 Landing page is invisible without JavaScript (below the hero)
- `globals.css:~110` sets `.landing-page .product-story, .feature-bento, .how-section, .security-section, .template-section, .faq-section, .final-cta { opacity: 0 }` **unconditionally**; they only become visible when `LandingMotion` adds `.is-visible`.
- Unlike the newer `data-anim` system (correctly gated behind the `js-anim` class added on mount), this older reveal system has no progressive-enhancement gate: with JS disabled the entire landing page below the hero never appears. Reduced-motion media queries restore visibility, but that's a different axis from JS availability.
- **Fix:** scope the hidden state under a JS-added class (mirror the `.js-anim` pattern).

### 3.2 Landing CTA `/vale-clinic` leads to a 404 in every seeded environment
- `page.tsx` ("View the published preview") links to `/vale-clinic`, but nothing creates that clinic: `scripts/seed_demo.py` seeds only `demo-collision-a`/`demo-collision-b`. Any visitor following the marketing CTA hits the (default, unbranded) 404 unless an operator manually creates a clinic with that exact slug and a published site.
- **Fix:** either seed a `vale-clinic` demo tenant with a published site, or point the CTA at a route that always renders.

### 3.3 Tenant-scoped background jobs never run in the self-hosted stack
- `docker-compose.yml` runs only `scripts/scan_worker.py` (public/patient media scanning).
- `app/worker.py` (exports, expired-artifact cleanup, retention cleanup, overdue follow-ups, document encryption) is only runnable via `infra/scheduler/run-clinic-worker.sh` — a **host-cron** entrypoint that is not part of the compose stack or CI.
- Net effect: a plain `docker compose up` deployment silently never cleans expired artifacts, never processes export jobs, never sends overdue follow-up notifications. **Fix:** add a scheduler/compose profile (documented clinic list or a controlled dispatcher) or at minimum a loud runbook warning.

---

## 4. Medium

### 4.1 Compose encryption-key fallback mismatch (worker vs api/migrate)
- `docker-compose.yml` gives `api`/`migrate` fallback `FIELD_ENCRYPTION_KEYS=l9E3deCfohbclkEMS8_mxCcgi-71x5H_f1f8sOmr1Jo=` but the `worker` service falls back to `dev-only-change-me-not-a-real-fernet-key`.
- When `docker.env` is absent (the "plain `docker compose up`" path the comments promise), the worker and API run with **different keys**: the media-scan worker cannot decrypt metadata the API encrypted — silent failures, not loud ones.
- Additionally, a **real-format Fernet key is committed** as the api/migrate default. The backend intentionally fails closed on missing `FIELD_ENCRYPTION_KEYS` in production; a committed default undermines that at the deployment layer, and the CI secret scan (PEM/tokens only) doesn't catch Fernet keys.
- **Fix:** make the fallback identical (or empty + startup failure), and never commit even a dev-format key.

### 4.2 Stale duplicate compose file
- `infra/docker/compose.yml` is an old variant of the root file: publishes Postgres on `0.0.0.0:5432`, hardcodes dev passwords, and lacks the `migrate`, `worker`, and `tunnel` services. `infra/docker/up.sh` actually uses the **root** compose file, so this one is dead but drifting. **Fix:** delete it or generate it from the root file.

### 4.3 Documentation is stale and mostly empty scaffolding
- `docs/project-summary.md` (updated as "current full project summary") still says the active branch is `feat/lead-activities` with PR #1 open and "250 tests" — reality: PR #2 merged, current branch `feat/premium-ui-animations`, 262 tests. `docs/claim-verification-2026-10-02.md` likewise says changes are "committed to no branch yet".
- Empty directories that imply missing docs: `docs/adr/`, `docs/requirements/`, `docs/runbooks/`, `docs/security/`, `docs/ux/` (only `docs/blueprint/adr/0001` exists).
- **No root `README.md`** and no docs index — onboarding depends entirely on tribal knowledge.
- **Fix:** refresh both docs, populate or delete the empty dirs, add a root README (quickstart: `infra/docker/up.sh`, seeded logins, env reference).

### 4.4 The "Lighthouse gate" doesn't gate anything
- CI runs Lighthouse mobile and uploads the JSON artifact, but **no step asserts a score threshold** — a 20/100 performance score would still pass. Docs describe it as a "gate". **Fix:** `npx lighthouse ... --assert` or a jq threshold check (e.g., fail under 0.8 performance).

### 4.5 e2e never touches the real backend
- The Playwright suite mocks every API call via `page.route` (great for stability), so no browser test ever exercises the real API + RLS + sessions through the UI. The only real-backend end-to-end check is `infra/smoke_api.py` (httpx, no browser). The composition is deliberate but leaves a coverage seam between the two layers (e.g., CSRF/cookie behavior through a real browser against the real API is untested). **Fix (optional):** one small unmocked e2e pass against the docker stack in the `docker-stack` CI job.

---

## 5. Minor / polish

1. **`artifacts/` is untracked clutter** — 4 preview PNGs sit untracked; CI also writes Lighthouse output there. Add `artifacts/` to `.gitignore` (only `docs/reports/*` are ignored today).
2. **`public/` has only `sw.js`** — no `favicon.ico`, `manifest.json`, or `apple-touch-icon`; `/favicon.ico` 404s on every deployment.
3. **Dead CSS path:** `[data-reveal]` styles + the `[data-reveal]` selector in `landing-motion.tsx` match **zero elements** in markup (the landing now uses `data-anim`). Remove or wire up.
4. **Hero double-animation:** `.landing-hero-copy` is both a `data-anim="stagger"` target (anime.js) *and* a CSS `hero-in` keyframe target — two overlapping reveal systems on the same nodes; also `.hero-proof` gets `--hero-index:4` while being excluded from the animation. Cosmetic redundancy.
5. **Motion maintainability trap:** `PremiumMotion` is mounted per-page (landing, dashboard). Since `js-anim` persists on `<html>`, any future page that adds `data-anim` attributes *without* rendering `PremiumMotion` will render permanently invisible content (the observer/fallback only run on mount). Worth a shared layout mount or a lint rule.
6. **`LandingMotion` scroll handler** updates the nav/progress bar on every scroll event with direct style writes; fine, but it doesn't gate the progress-bar transform on reduced motion (CSS hides the element, so impact is nil — noted for tidiness).
7. **5 × `eslint-disable no-unused-vars`** across panels (`forms-panel`, `tools-panel`, `theme-panel`, `provider-select`, `seo-panel`) — likely stale after refactors; worth a sweep.
8. **3 × `<img>` warnings** on `[clinicSlug]/site-view.tsx` — clinic website images bypass `next/image` (LCP/bandwidth on the customer-facing surface).
9. **`env.example` is missing supported vars:** `VAPID_SUBJECT`, `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY` (browser push) and `FORWARDED_ALLOW_IPS` / `ALLOW_WILDCARD_FORWARDED_IPS` are all read by `core/config.py` but absent from the reference file. `RUN_MIGRATIONS_ON_START` is documented while the compose stack actually uses a dedicated `migrate` service (slight drift).
10. **CI has no dependency caching** (`pip`/`npm`) — pure speed cost on every run.
11. **tsconfig:** `strict` is on (good); `noUncheckedIndexedAccess` is off — would catch a class of index bugs if desired.
12. **Workspace nav has no `/settings`** page; account management lives indirectly under `/security`. Fine for now, but the nav omits any account entry point (ties into 2.2).

---

## 6. Recommended fix order

1. **2.1** Migration stranding (data-plane risk; unblocks every environment).
2. **2.2** Logout + account menu (small change, large security win).
3. **2.3** Error/not-found boundaries (small, protects every surface).
4. **3.3** Background jobs in the self-hosted stack (silent data-hygiene gap).
5. **4.1 / 4.2** Compose key mismatch + dead compose file.
6. **3.1 / 3.2** Landing no-JS visibility + `/vale-clinic` target.
7. **4.4** Make Lighthouse actually gate; **4.3 / README** docs refresh.
8. Everything in §5 as a cleanup batch.

---

## 7. Environment notes from this review session

- The 7 test failures seen against the *running* local stack were caused solely by 2.1 (stale schema at `0055`); all pass on a freshly migrated database.
- `docker.env` exists locally and defines `FIELD_ENCRYPTION_KEYS`, so the 4.1 fallback mismatch is dormant in this environment — it bites only when `docker.env` is missing.
- The 2 skipped backend tests are the Supabase storage tests (config-gated by design).

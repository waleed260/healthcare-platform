# Phase 13 release traceability

| Requirement | Evidence | State |
| --- | --- | --- |
| CI API/web gates | `.github/workflows/ci.yml` runs migrations, safe head downgrade/re-upgrade, offline SQL generation, API tests, Python dependency audit, high-confidence private-key scan, web build, and npm dependency audit | Implemented; full CI execution remains to be exercised in a hosted runner |
| Container packaging | CI builds the API image and the production standalone Next.js image; local Compose retains a separate hot-reload development image | Implemented; hosted build remains to be exercised |
| Contract/type gates | CI regenerates the committed OpenAPI artifact and the finite TypeScript literal types in `packages/contracts/openapi-types.ts`, then runs the frontend TypeScript check before build | Implemented |
| Environment contract | `Settings` accepts only the specification's `local`, `test`, `staging`, and `production` environments; the example configuration and regression test use the same contract | Implemented |
| Redacted observability | `app/core/observability.py` configures structured JSON request logs and optional Sentry initialization; the `before_send` hook removes request bodies, cookies, headers, query tokens, user identity, breadcrumbs, and credential-like extras | Implemented locally; provider alert routing and production drill remain open |
| Backup creation | `infra/backup/backup.sh` creates a custom-format dump, validates its catalog, and emits a checksum | Implemented |
| Restore verification | `infra/backup/restore-verify.sh` requires an isolated target, verifies checksum, restores, and checks migration/RLS evidence | Implemented |
| Accessibility/performance gates | Playwright smoke suite covers desktop/mobile core surfaces, synthetic onboarding, booking submissions, manual password reset, first-login MFA enrollment, website draft publishing, clean private-document signed downloads, platform retention approval/assignment, follow-up/notification operations, the tablet-viewport reception queue critical path, and privacy workflow controls; axe checks all implemented public/staff/platform routes; `infra/performance/load_profile.py` provides synthetic 20 req/s, 50-session profiles with exact short-lived cookie rotation and p95 thresholds; local execution passes all 88 browser tests | Partial; staging load execution and manual WCAG evidence remain open |
| Dependency readiness | `/health/ready` checks PostgreSQL plus local private/public roots or both configured Supabase buckets with bounded timeouts and generic failure responses | Implemented locally; provider-backed staging evidence remains open |
| Production launch gates | Secrets, TLS, monitoring, scanner/storage provider, and pilot approval | Open |

`infra/release_gate.py` and `docs/runbooks/release-gate.md` provide a fail-closed
validator for the numeric and boolean launch gates. This does not mark them
complete: staging load/restore execution, manual WCAG review, provider/TLS
evidence, retention approval, monitoring drills, and pilot owner approval still
require external release activity.

`docs/runbooks/production-readiness-checklist.md` provides the evidence
template and execution sequence for the manual WCAG review, alert/rollback
drill, isolated restore record, retention approval, and pilot acceptance.

The API now exposes platform-admin-only `GET /api/v1/admin/metrics`, with
bounded request counts, p50/p95/p99 latency samples, status-code counts,
database-pool size/checked-out/overflow gauges, appointment outcome totals,
pending document/media scan backlog, and storage/publish job failures. Metrics
use FastAPI route templates rather than raw URLs, so IDs and patient data cannot
become labels. Provider alert routing and production drill evidence remain
external launch gates.

Production configuration now fails closed for local database defaults, missing
migration credentials, non-HTTPS public/app origins, missing encryption keys,
and missing cookie domain. `FIELD_ENCRYPTION_KEYS` is accepted as the canonical
environment name while retaining the local singular alias.

The scripts intentionally do not encrypt or upload data themselves: production
must bind them to the approved KMS and object-storage controls rather than
silently introducing local plaintext retention.

The API dependencies are pinned, including FastAPI `0.141.1`, cryptography
`50.0.1`, bleach `6.4.0`, pytest `9.1.1`, and dnspython `2.7.0`; FastAPI
resolves Starlette `1.6.0` in the local compatibility check. The authoritative
vulnerability result is produced by the CI `pip-audit` step.

The web runtime is pinned to Next.js `16.3.5`, with TypeScript `6.0.3`, ESLint
CLI configuration, Playwright `1.63.0`, and axe-core browser checks. The
committed workspace `package-lock.json` and CI's `npm ci` make installation
reproducible; local offline `npm audit --audit-level=high` passes, while hosted
CI remains the authoritative network-backed audit result.
Next's production build uses its compiler-API TypeScript checker because the
detached TypeScript 6 CLI runner does not emit parseable `--showConfig` output
in this environment; CI still runs the independent `npx tsc --noEmit` check.

The web boundary now uses `apps/web/proxy.ts` to generate a per-response CSP
nonce and propagate it to Next's server-rendered scripts/styles. It also emits
`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
`Permissions-Policy`, and production-only HSTS. Browser coverage asserts the
nonce-based policy and anti-clickjacking headers.

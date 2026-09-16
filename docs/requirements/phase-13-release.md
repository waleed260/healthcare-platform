# Phase 13 release traceability

| Requirement | Evidence | State |
| --- | --- | --- |
| CI API/web gates | `.github/workflows/ci.yml` runs migrations, safe head downgrade/re-upgrade, offline SQL generation, API tests, Python dependency audit, high-confidence private-key scan, web build, and npm dependency audit | Implemented; full CI execution remains to be exercised in a hosted runner |
| Container packaging | CI builds the API image and the production standalone Next.js image; local Compose retains a separate hot-reload development image | Implemented; hosted build remains to be exercised |
| Contract/type gates | CI verifies the committed OpenAPI artifact from the repository root and runs the frontend TypeScript check before build | Implemented |
| Backup creation | `infra/backup/backup.sh` creates a custom-format dump, validates its catalog, and emits a checksum | Implemented |
| Restore verification | `infra/backup/restore-verify.sh` requires an isolated target, verifies checksum, restores, and checks migration/RLS evidence | Implemented |
| Accessibility/performance gates | Playwright smoke suite covers desktop/mobile core surfaces, synthetic onboarding and booking submissions; axe checks all implemented public/staff routes; `infra/performance/load_profile.py` provides synthetic 20 req/s, 50-session profiles with p95 thresholds; 42 browser tests are currently listed | Partial; staging load execution and manual WCAG evidence remain open |
| Production launch gates | Secrets, TLS, monitoring, scanner/storage provider, and pilot approval | Open |

`infra/release_gate.py` and `docs/runbooks/release-gate.md` provide a fail-closed
validator for the numeric and boolean launch gates. This does not mark them
complete: staging load/restore execution, manual WCAG review, provider/TLS
evidence, retention approval, monitoring drills, and pilot owner approval still
require external release activity.

The API now exposes platform-admin-only `GET /api/v1/admin/metrics`, with
bounded request counts, p50/p95/p99 latency samples, status-code counts, and
database-pool size/checked-out/overflow gauges. Metrics use FastAPI route
templates rather than raw URLs, so IDs and patient data cannot become labels.

Production configuration now fails closed for local database defaults, missing
migration credentials, non-HTTPS public/app origins, missing encryption keys,
and missing cookie domain. `FIELD_ENCRYPTION_KEYS` is accepted as the canonical
environment name while retaining the local singular alias.

The scripts intentionally do not encrypt or upload data themselves: production
must bind them to the approved KMS and object-storage controls rather than
silently introducing local plaintext retention.

The API dependency audit currently reports no known vulnerabilities after pinning
FastAPI `0.141.1`, cryptography `50.0.1`, bleach `6.4.0`, pytest `9.1.1`, and
dnspython `2.7.0`; FastAPI resolves Starlette `1.6.0` in the isolated check.

The web runtime is pinned to Next.js `16.3.5`, with TypeScript `6.0.3`, ESLint
CLI configuration, Playwright `1.63.0`, and axe-core browser checks. The current
`npm audit` scan reports zero vulnerabilities. The Next 16 build uses its CLI
TypeScript checker explicitly so the production build and CI use the same
validated path.

The web boundary now uses `apps/web/proxy.ts` to generate a per-response CSP
nonce and propagate it to Next's server-rendered scripts/styles. It also emits
`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
`Permissions-Policy`, and production-only HSTS. Browser coverage asserts the
nonce-based policy and anti-clickjacking headers.

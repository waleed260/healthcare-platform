# Claim verification & fixes — multi-LLM review of the Clinic CRM + Website SaaS

- **Date:** 2026-10-02
- **Branch:** `feat/lead-activities`
- **Source:** `claim.docx` — a GLM 5.3 review + an "independent repository review" of this repo.
- **What this is:** each claim checked against the *live* code (not the supplied ZIP), my verdict, and the fix that landed. Verified with the real backend suite **(249 passed, 2 skipped)**, `tsc --noEmit` clean, ESLint 0 errors, and three new PostgreSQL integration tests run against a migrated database.

## Headline

Both reviews are directionally right on the two things that matter: the **login lockout is dead code** and **patient merge silently orphans most of a patient's data**. The independent review is the stronger of the two — it correctly adds `invoices`, fixes GLM's `package_sessions`/`clinical_form_submissions` mistakes, and refuses to over-claim the `.env.save` leak. Neither review was complete: the merge gap is **wider still** (`privacy_requests`, `export_jobs`), and there is a **separate latent bug in `duplicate_candidates`** that neither caught. All confirmed items are now fixed.

---

## Disposition table

| # | Claim | My verdict | Fix |
|---|-------|-----------|-----|
| 1 | Login rate-limit rollback erases the failure counter | ✅ **Confirmed — real security bug** | Failures now commit on an independent session; can't be rolled back by login. New integration test proves persist → lock → expire → clear. |
| 2 | Patient merge incomplete | ✅ **Confirmed, and broader than reported** | New central `merge.py` service with an explicit registry covering **all 17** patient-scoped tables. |
| 3 | GLM: `package_sessions` is direct `patient_id` | ✅ Independent review correct — it's `patient_package_id` | Not repointed directly; follows `patient_packages`. Verified by test. |
| 4 | GLM: table is `clinical_form_submissions` | ✅ Independent review correct — it's `clinical_form_responses` | Correct name repointed. |
| 5 | `invoices` omitted (GLM missed) | ✅ **Confirmed** | `invoices` repointed; `invoice_lines`/`payments` follow via `invoice_id`. Verified by test. |
| 6 | Public gallery `max-age=300` vs. immediate revocation | ✅ **Confirmed** | Image now `Cache-Control: private, no-store`; list hint aligned. |
| 7 | `--forwarded-allow-ips=*` spoofable | ✅ **Valid, deployment-dependent** | Made configurable (default `127.0.0.1`); compose trusts only its pinned subnet; production config **rejects `*`** unless explicitly overridden. |
| 8 | Search ILIKE `%`/`_` wildcards | ✅ **Confirmed hardening** | `%`, `_`, `\` escaped with `ESCAPE '\'` in patient search and duplicate-candidates. |
| 9 | Unpaginated patient-scoped lists | ✅ **Valid scalability issue** | **Deferred** (see below) — needs API-contract + frontend changes; not a correctness bug. |
| 10 | Patient number collision, no retry | ✅ **Valid low-probability bug** | `patient_create` now retries on the unique violation inside a savepoint. |
| 11 | Login lacks origin validation | ✅ **Valid hardening** | `_validate_origin` added to `login`. |
| 12 | CSRF compared with `!=` not constant-time | ✅ **Theoretical hardening** | `verify_csrf` now uses `hmac.compare_digest`. |
| 13 | MFA commit/cookie ordering | ⚠️ **Minor robustness** | **Deferred** — low priority; noted below. |
| 14 | `duplicate_candidates` lacks origin validation | ✅ **Valid consistency** | `_validate_origin` added. |
| 15 | `provider_user_id` not validated | ⚠️ **Not proven as a vuln (FK already scopes it)** | Added an explicit active-clinic-user check anyway for a clean error + no disabled-account attribution. |
| 16 | `.env.save` secret | ❎ **Not a leak (verified on the live tree)** | `.env`, `.env.save`, `docker.env` are git-ignored (mode 0600) and **never** appear in history. No action needed. |

---

## Beyond the reviews — my own findings

### A. Latent runtime bug in `duplicate_candidates` (neither review caught)
`crm/routes.py` built the query with `text("""… {_patient_scope_sql('p')} …""")` **without an `f` prefix**, so the `{…}` placeholder was shipped to PostgreSQL literally — a guaranteed `syntax error at or near "{"` the moment the endpoint runs. It went unnoticed because the integration tests that would hit it are DB-gated. **Fixed** (converted to an f-string; the scope SQL now interpolates correctly).

### B. Merge gap is wider than either review
The database has **17** tables with a `patient_id` column. Both reviews stopped at ~15. The merge now also repoints **`privacy_requests`** and **`export_jobs`** (a patient's data-subject/compliance history), so a GDPR-style request trail follows the surviving patient instead of being stranded on the tombstone. A structural guard test (`test_merge_registry_covers_every_patient_scoped_table`) queries `information_schema` and **fails if any future migration adds a patient-owned table that isn't registered** — so this class of bug can't silently reappear.

### Merge conflict rules made explicit
- **`clinical_tool_states`** has `UNIQUE (clinic_id, patient_id, tool_key)`; a blind repoint would collide. Rule: **target wins** — the source's conflicting tool rows are dropped, non-conflicting ones move. Proven by test.
- **Membership tables** (`patient_care_team`, `patient_tags`) dedupe via `INSERT … ON CONFLICT DO NOTHING` then delete source.
- **Indirect children** (`invoice_lines`, `payments`, `package_sessions`, `treatment_plan_items`) are documented as following their parent FK and are asserted to stay attached.
- Source is **tombstoned** (`status='merged'`, `duplicate_of=target`), never hard-deleted; an immutable `patient_merge_events` row is written with per-table counts returned to the caller.

---

## Previously deferred — now also done

- **Cursor pagination** (claim #9). `media` and `notes` (the genuinely high-volume patient lists) got keyset cursor pagination (`cursor`+`limit`, default 100/max 200, `next_cursor` in meta) following the `patient_list` template; `care-team` and `history` (small / already sliced) got bounded `LIMIT` caps on their underlying queries. Backward-compatible; OpenAPI contract regenerated.
- **MFA commit/cookie ordering** (claim #13). `mfa_verify` now stages the rotated cookies **before** `db.commit()` (matching `/login`), so a commit failure rolls back and leaves the old session valid instead of rotating in the DB but never delivering the new token.
- **Historical reconciliation job** (doc §10). `apps/api/scripts/reconcile_merges.py` — a strictly read-only scan keyed off `patient_merge_events` that reuses the merge registry to report orphaned rows (and un-tombstoned sources) per merge, with `--json` and `--fail-on-findings`. Covered by an integration test. It reports only; clinical/financial conflicts are left for a human against a backup.

---

## Release gate (from the doc) — status

1. ✅ Durable login rate limiting + real-Postgres integration test — **done, passing.**
2. ✅ Complete merge coverage incl. invoices/packages/clinical/compliance + conflict rules — **done, passing.**
3. ✅ Patient-media revocation-safe cache policy — **done.**
4. ✅ Forwarded-IP trust hardened + production guard — **done.**
5. ◻️ Run against a production-like Postgres in CI — the tests are written and pass locally against a migrated DB; CI already has a Postgres service.
6. ◻️ Pagination / reconciliation job — deferred as above.

Changes are committed to no branch yet — they sit uncommitted on `feat/lead-activities` for review.

# Gate 4 report — one-command evidence collector

## Implementation

`scripts/verify-all.sh` is the host-side evidence command for the new brief.
It writes timestamped output to `docs/reports/evidence/` and fails closed when
the migrator/runtime PostgreSQL URLs or `psql` are missing.

The phases are:

- Alembic migrations and two deterministic seed passes.
- Direct runtime-role `psql` checks for clinic A counts and clinic-B visibility.
- `infra/verify_seed.py` and the full API suite.
- ESLint with `--max-warnings=0`, TypeScript, and the production build.
- All Playwright specs in shuffled order.
- The tenant negative control, which must fail with `Synthetic Patient B` in
  the failure output; browser-startup failures are rejected as insufficient.
- Lighthouse mobile performance when the `lighthouse` binary is installed;
  otherwise the log records an explicit optional-tool skip.

## Local evidence

- `bash -n scripts/verify-all.sh` — passed.
- Host execution is pending because PostgreSQL and `psql` are not available in
  this environment. See `docs/reports/pending-human.md`.

# Gate 0 environment unblock

Run these commands from the real repository clone, not a temporary copy. Do
not paste credentials, tokens, or command output containing secrets into chat.

## Repository and Git metadata

The agent must be able to create `.git/index.lock` in the real clone. Verify
before asking for a commit:

```bash
git status --short
git diff --check
git add -A
git commit -m "feat(admin): complete governance gates [REQ-9.3, REQ-14, REQ-16]"
```

If Git writes are intentionally unavailable, leave the worktree intact and
run the commit and push yourself after reviewing the diff.

## PostgreSQL and seed evidence

Start the project database and confirm its health:

```bash
docker compose up -d postgres
docker compose ps
```

From `apps/api`, use the repository's runtime and seed roles. Keep passwords in
the shell environment or secret store; never commit them:

```bash
export DATABASE_URL='postgresql+psycopg://<migrator>@localhost:5432/healthcare'
export SEED_DATABASE_URL="$DATABASE_URL"
export TEST_ADMIN_DATABASE_URL="$DATABASE_URL"
export TEST_DATABASE_URL='postgresql+psycopg://<runtime>@localhost:5432/healthcare'
alembic upgrade head
PYTHONPATH=. python scripts/seed_demo.py
PYTHONPATH=. python scripts/seed_demo.py
PYTHONPATH=../.. python ../../infra/verify_seed.py
PYTHONPATH=. pytest
```

The twice-run seed and `infra/verify_seed.py` output are the authoritative
evidence for counts and clinic-scoped visibility. Record any remaining skip
with its exact reason in `docs/reports/completion-audit.md`.

## GitHub CI evidence

Authenticate locally with the device flow or an already-configured secure
credential, then collect the latest run URL and failed logs:

```bash
gh auth status
gh run list --branch main --limit 3
gh run view <run-id> --log-failed
```

Do not use a token in a command copied into chat. Record the run URL only after
API, container, and web jobs are green.

## Browser and negative control

The Playwright config keeps the workaround opt-in:

```bash
cd apps/web
PW_NO_SANDBOX=1 npx playwright test --project=chromium
BREAK_TENANT_ISOLATION=1 PW_NO_SANDBOX=1 \
  npx playwright test tenant-isolation.spec.ts --project=chromium
```

The normal suite must pass. The deliberate negative run must fail on the
tenant assertion, not during browser startup. If the bundled browser is
unusable, point the config at a host-installed browser with
`PW_CHROMIUM_EXECUTABLE_PATH=/path/to/chrome`.

## Lighthouse artifact

With the production web server running on port 3000:

```bash
npx --yes lighthouse http://127.0.0.1:3000/ \
  --form-factor=mobile --only-categories=performance --output=json \
  --output-path=docs/reports/lighthouse-mobile.json \
  --chrome-flags="--headless --no-sandbox"
```

Review LCP, CLS, and TBT, then retain the JSON artifact. CI performs the same
measurement and uploads `lighthouse-gate-0-mobile.json`.

# Pilot-load verification

This runbook records performance evidence for the release gate. Use synthetic
fixtures only; never place patient identifiers, real appointment data, or
production secrets in a request plan or result artifact.

## Target thresholds

| Profile | p95 target |
| --- | ---: |
| API list/detail | 500 ms |
| Availability for a 31-day range | 800 ms |
| Booking command | 1,500 ms |
| Staff dashboard critical path | 2,500 ms |

The pilot profile is 50 concurrent staff sessions, a 20 requests/second burst
for 60 seconds, 1M appointments across test tenants, and a 100k-patient large
clinic. Availability, booking correctness under concurrency, tenant isolation,
and database saturation must be checked separately from the HTTP latency rollup.

## Run

Create a local, synthetic-only request plan. The body may contain generated UUIDs
and dates, but must not contain real patient data.

```bash
export ALLOW_SYNTHETIC_LOAD=YES
python3 infra/performance/load_profile.py \
  --base-url https://staging.example.invalid \
  --profile api-list \
  --request-plan /secure/path/synthetic-api-list.json \
  --duration 60 --rate 20 --concurrency 50 --sessions 50 \
  --session-cookie-file /secure/path/short-lived-synthetic-cookies.txt \
  > /secure/path/load-api-list.json
```

For an authenticated staff profile, the cookie file must contain exactly one
short-lived synthetic staging `Cookie` header per session. The tool rotates
these headers across requests and reports the authenticated session count
without writing cookie values to the result. Public-only profiles may omit the
file and will report zero authenticated sessions.

Use `--profile availability`, `--profile booking`, or `--profile dashboard`
for the corresponding threshold. Set `LOAD_AUTHORIZATION` and/or `LOAD_COOKIE`
only with short-lived staging credentials. The tool adds an explicit
`X-Synthetic-Load: true` header and returns a non-zero exit status when p95 or
the configured error budget is exceeded. `--dry-run` validates configuration
without making requests.

## Evidence to attach to the release

Record the deployment version, database tier, worker count, dataset cardinality,
request plan hash, start/end UTC timestamps, result JSON, p50/p95/p99, observed
throughput, status counts, error count, and resource graphs. Attach the booking
concurrency result and a cross-tenant read/write isolation result. The release
owner signs off only after these artifacts are stored in the approved restricted
location and synthetic credentials are revoked.

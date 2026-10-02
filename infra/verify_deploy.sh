#!/usr/bin/env bash
# Verify a running API (local Docker, tunnel or any host). Usage: infra/verify_deploy.sh https://your-api.example
set -euo pipefail
BASE="${1:?usage: verify_deploy.sh <base-url>}"
retry() { for _ in $(seq 1 30); do "$@" && return 0; sleep 4; done; return 1; }  # free tiers cold-start
retry curl -fsS "$BASE/health" >/dev/null && echo "health        ok"
retry curl -fsS "$BASE/health/ready" >/dev/null && echo "ready (db+storage) ok"
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/v1/auth/me"); [ "$code" = 401 ] && echo "auth guard    ok (401)" || { echo "auth/me returned $code"; exit 1; }
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/v1/public/sites/slug/no-such-clinic"); [ "$code" = 404 ] && echo "db read       ok (404)" || { echo "public site returned $code"; exit 1; }
echo "all checks passed"

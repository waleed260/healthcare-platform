#!/usr/bin/env bash
# Start the stack. Options: --public (open a Cloudflare quick tunnel and print its https URL), --down
set -euo pipefail
cd "$(dirname "$0")/../.."
[ -e docker.env ] || infra/docker/init-env.sh
COMPOSE=(docker compose --env-file docker.env)
case "${1:-}" in
  --down) "${COMPOSE[@]}" --profile public down; exit 0 ;;
  --public) PROFILE=(--profile public) ;;
  *) PROFILE=() ;;
esac
"${COMPOSE[@]}" "${PROFILE[@]}" up -d --build
bash infra/verify_deploy.sh http://127.0.0.1:8000
if [ "${1:-}" = "--public" ]; then
  for _ in $(seq 1 30); do
    url=$("${COMPOSE[@]}" --profile public logs tunnel 2>&1 | grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1 || true)
    [ -n "$url" ] && { echo "PUBLIC API URL: $url"; echo "Point the frontend at it: infra/docker/point-vercel.sh $url"; exit 0; }
    sleep 2
  done
  echo "tunnel URL not found yet; run: docker compose --profile public logs tunnel"
fi

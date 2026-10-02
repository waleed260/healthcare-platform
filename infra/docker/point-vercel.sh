#!/usr/bin/env bash
# Point the Vercel frontend at the API URL and redeploy. API_URL is read at build time by next.config.ts.
#   infra/docker/point-vercel.sh https://something.trycloudflare.com
# Quick-tunnel URLs change on every tunnel restart, so rerun this after restarting the tunnel.
set -euo pipefail
URL="${1:?usage: point-vercel.sh <https api url>}"
case "$URL" in https://*) ;; *) echo "API URL must be https"; exit 1 ;; esac
cd "$(dirname "$0")/../.."
vercel env rm API_URL production --yes >/dev/null 2>&1 || true
printf '%s' "$URL" | vercel env add API_URL production >/dev/null
vercel deploy --prod --yes

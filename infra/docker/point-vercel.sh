#!/usr/bin/env bash
# Point the Vercel frontend at the API URL and redeploy. API_URL is read at build time by next.config.ts.
#   infra/docker/point-vercel.sh https://something.trycloudflare.com
# Quick-tunnel URLs change on every tunnel restart, so rerun this after restarting the tunnel.
set -euo pipefail
URL="${1:?usage: point-vercel.sh <https api url>}"
case "$URL" in https://*) ;; *) echo "API URL must be https"; exit 1 ;; esac
cd "$(dirname "$0")/../.."
vercel env rm API_URL production --yes >/dev/null 2>&1 || true
# Use --value (not stdin): the Vercel CLI runs --non-interactive by default when
# it detects an automation/agent, which silently ignores a piped stdin value and
# stores an EMPTY string. --no-sensitive keeps it readable so `vercel env pull`
# can confirm it. (API_URL is a public URL, not a secret.)
vercel env add API_URL production --value "$URL" --no-sensitive --yes >/dev/null
vercel deploy --prod --yes

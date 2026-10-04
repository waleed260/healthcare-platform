#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# tunnel-guard.sh — self-healing Cloudflare quick-tunnel watchdog.
#
# The free `trycloudflare.com` quick tunnel used to expose the local API to the
# Vercel frontend is EPHEMERAL: Cloudflare revokes it after a few hours and the
# URL changes on every container restart. When that happens cloudflared loops on
# "Unauthorized: Tunnel not found", the live site 502s, and every workspace page
# looks empty. This watchdog detects that, restarts the tunnel, reads the new
# URL, and updates + redeploys Vercel automatically.
#
# SETUP (one time):
#   1. Create a Vercel token: https://vercel.com/account/tokens  → copy it.
#   2. Put these in infra/tunnel-guard.env (or export them):
#        VERCEL_TOKEN=xxxxxxxx
#        VERCEL_PROJECT=healthcare-crm          # project name or id
#        VERCEL_TEAM=httpsgithubcomwaleed260codedebugger   # team/scope slug (optional)
#        API_URL_ENV_KEY=API_URL                # the env var the frontend reads
#        TUNNEL_CONTAINER=clinic-tunnel-1
#        CHECK_INTERVAL=60                       # seconds between health checks
#   3. Run it:  nohup bash infra/tunnel-guard.sh >> /tmp/tunnel-guard.log 2>&1 &
#      (or add the systemd unit in infra/tunnel-guard.service)
#
# A stabler long-term option that NEEDS NO redeploys is a reserved URL
# (ngrok free static domain, or a Cloudflare *named* tunnel) — see README.
# ---------------------------------------------------------------------------
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$HERE/tunnel-guard.env" ] && . "$HERE/tunnel-guard.env"

TUNNEL_CONTAINER="${TUNNEL_CONTAINER:-clinic-tunnel-1}"
API_URL_ENV_KEY="${API_URL_ENV_KEY:-API_URL}"
CHECK_INTERVAL="${CHECK_INTERVAL:-60}"
VERCEL_API="https://api.vercel.com"
TEAM_Q=""
[ -n "${VERCEL_TEAM:-}" ] && TEAM_Q="?slug=${VERCEL_TEAM}"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

vercel() { # method path [json-body]
  local method="$1" path="$2" body="${3:-}"
  local url="$VERCEL_API$path"
  if [ -n "$body" ]; then
    curl -s -X "$method" "$url" -H "Authorization: Bearer $VERCEL_TOKEN" -H "Content-Type: application/json" -d "$body"
  else
    curl -s -X "$method" "$url" -H "Authorization: Bearer $VERCEL_TOKEN"
  fi
}

current_tunnel_url() {
  docker logs "$TUNNEL_CONTAINER" 2>&1 | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1
}

tunnel_alive() { # url -> 0 if /health 200
  local url="$1"; [ -z "$url" ] && return 1
  [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$url/health" 2>/dev/null)" = "200" ]
}

restart_tunnel_get_url() {
  log "restarting $TUNNEL_CONTAINER …"
  docker restart "$TUNNEL_CONTAINER" >/dev/null 2>&1
  local old="$1" url=""
  for _ in $(seq 1 30); do
    sleep 3
    url="$(current_tunnel_url)"
    if [ -n "$url" ] && [ "$url" != "$old" ] && tunnel_alive "$url"; then echo "$url"; return 0; fi
  done
  echo ""; return 1
}

# Resolve the Vercel project id + the env var's id (once; refreshed on failure).
PROJECT_ID=""; ENV_ID=""
resolve_ids() {
  local proj; proj="$(vercel GET "/v9/projects/${VERCEL_PROJECT}${TEAM_Q}")"
  PROJECT_ID="$(echo "$proj" | grep -oE '"id":"[^"]+"' | head -1 | cut -d'"' -f4)"
  [ -z "$PROJECT_ID" ] && { log "could not resolve project id (check token/project)"; return 1; }
  local envs; envs="$(vercel GET "/v9/projects/${PROJECT_ID}/env${TEAM_Q}")"
  # grab the id of the env whose key == API_URL_ENV_KEY
  ENV_ID="$(echo "$envs" | tr ',' '\n' | grep -B2 "\"key\":\"${API_URL_ENV_KEY}\"" | grep -oE '"id":"[^"]+"' | head -1 | cut -d'"' -f4)"
  [ -z "$ENV_ID" ] && { log "could not resolve env id for ${API_URL_ENV_KEY}"; return 1; }
  return 0
}

update_and_redeploy() { # new_url
  local new="$1"
  [ -z "$PROJECT_ID" ] || [ -z "$ENV_ID" ] && resolve_ids || true
  resolve_ids || return 1
  log "updating Vercel ${API_URL_ENV_KEY} -> $new"
  vercel PATCH "/v9/projects/${PROJECT_ID}/env/${ENV_ID}${TEAM_Q}" "{\"value\":\"${new}\",\"target\":[\"production\"]}" >/dev/null
  # redeploy: prefer a deploy hook if provided, else create a deployment from main
  if [ -n "${VERCEL_DEPLOY_HOOK:-}" ]; then
    curl -s -X POST "$VERCEL_DEPLOY_HOOK" >/dev/null && log "redeploy triggered (deploy hook)"
  else
    vercel POST "/v13/deployments${TEAM_Q}" "{\"name\":\"${VERCEL_PROJECT}\",\"project\":\"${PROJECT_ID}\",\"target\":\"production\",\"gitSource\":{\"type\":\"github\",\"ref\":\"main\"}}" >/dev/null && log "redeploy triggered (api)"
  fi
}

log "tunnel-guard started (container=$TUNNEL_CONTAINER, interval=${CHECK_INTERVAL}s)"
[ -z "${VERCEL_TOKEN:-}" ] && { log "FATAL: VERCEL_TOKEN not set — see setup header"; exit 1; }

LAST_PUSHED=""
while true; do
  URL="$(current_tunnel_url)"
  if ! tunnel_alive "$URL"; then
    log "tunnel DOWN (url=${URL:-none}) — healing"
    NEW="$(restart_tunnel_get_url "$URL")"
    if [ -n "$NEW" ]; then
      log "tunnel back up: $NEW"
      update_and_redeploy "$NEW" && LAST_PUSHED="$NEW"
    else
      log "tunnel did not recover this cycle; will retry"
    fi
  elif [ -n "$URL" ] && [ "$URL" != "$LAST_PUSHED" ]; then
    # tunnel is alive but Vercel may still point at an older URL — reconcile once.
    if [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "${SITE_URL:-https://web-eight-flax-pmiw08soee.vercel.app}/api/v1/auth/me" 2>/dev/null)" = "502" ]; then
      log "live site 502 though tunnel up — syncing Vercel to $URL"
      update_and_redeploy "$URL" && LAST_PUSHED="$URL"
    else
      LAST_PUSHED="$URL"
    fi
  fi
  sleep "$CHECK_INTERVAL"
done

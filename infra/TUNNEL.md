# Exposing the local API to the Vercel frontend

The Vercel site talks to the API running on this machine through a tunnel, and
`API_URL` (a Vercel env var) must point at that tunnel's URL.

## The problem with the current setup (free Cloudflare quick tunnel)

`docker-compose.yml` runs `cloudflared` as a **free quick tunnel**
(`*.trycloudflare.com`). That URL is **ephemeral**:

- it changes on every `docker restart` of the tunnel, and
- Cloudflare **revokes** it after a few hours, after which cloudflared loops on
  `Register tunnel error ... "Unauthorized: Tunnel not found"` and never
  self-heals.

When that happens the live site returns **502** on every `/api/...` call, so
the dashboard/website show "connection could not be checked" and look empty.

## Option A — self-healing watchdog (works with the current quick tunnel)

`infra/tunnel-guard.sh` watches the tunnel and, when it dies, restarts it, reads
the new URL, and updates + redeploys Vercel automatically (~1–2 min of downtime
per event, then it's back on its own).

```bash
cp infra/tunnel-guard.env.example infra/tunnel-guard.env   # fill in VERCEL_TOKEN
nohup bash infra/tunnel-guard.sh >> /tmp/tunnel-guard.log 2>&1 &
# or install the systemd unit:
#   sudo cp infra/tunnel-guard.service /etc/systemd/system/
#   sudo systemctl enable --now tunnel-guard
```

It needs a Vercel token (https://vercel.com/account/tokens). This keeps the
site working unattended, but there is still a short blip each time the tunnel
dies, and it burns a redeploy each time.

## Option B — a reserved URL that never changes (recommended, no redeploys) ✅

Give the tunnel a **stable hostname** so `API_URL` is set once and never again.

**B1. ngrok free static domain** (recommended — the `tunnel-ngrok` service is
already wired up in `docker-compose.yml`):
1. Sign up at https://ngrok.com (free), copy your authtoken.
2. Claim your one free static domain (Dashboard → Domains), e.g.
   `your-clinic.ngrok-free.app`.
3. Add to `docker.env`:
   ```
   NGROK_AUTHTOKEN=2abc...your-token
   NGROK_DOMAIN=your-clinic.ngrok-free.app
   ```
4. Start it (and stop the old quick tunnel):
   ```
   docker compose stop tunnel
   docker compose --profile ngrok up -d tunnel-ngrok
   ```
5. Set Vercel `API_URL=https://your-clinic.ngrok-free.app` **once** and redeploy.
   The URL never changes again — no watchdog, no redeploys, no breakage.

**B2. Cloudflare *named* tunnel** (free, needs a domain on Cloudflare):
`cloudflared tunnel login` → `cloudflared tunnel create clinic` → route a
hostname (`api.yourdomain.com`) → run with `--config`/token. Stable hostname,
same "set `API_URL` once" benefit.

## Option C — host the API properly

Deploy the backend to Render/Fly/Railway/a VPS with its own stable HTTPS URL and
point `API_URL` at it. No tunnel at all. Best for anything beyond local demos.

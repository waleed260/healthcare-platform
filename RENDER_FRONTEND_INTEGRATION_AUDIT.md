# Frontend Integration Audit

## API URL Configuration

**Source**: `apps/web/next.config.ts:15`

```typescript
const apiOrigin = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
```

- `API_URL` is a **server-side** env var (no `NEXT_PUBLIC_` prefix needed, but `NEXT_PUBLIC_API_URL` is accepted as fallback).
- Default is `http://localhost:8000` — will fail on Vercel if not set. **The Vercel build does not fail**, but API calls will fail at runtime because `localhost:8000` doesn't exist on Vercel's edge.
- The URL is validated: must be absolute HTTP(S), not empty.

**Current Vercel value**: Must be set to the Render service URL (e.g., `https://healthcare-api-xxxx.onrender.com`).

## Rewrite Rules

```typescript
return [
  { source: "/api/:path*", destination: `${apiOrigin}/api/:path*` },
  { source: "/health/:path*", destination: `${apiOrigin}/health/:path*` },
  { source: "/:clinicSlug/sitemap.xml", destination: "/:clinicSlug/sitemap-feed" },
];
```

- All `/api/*` requests are proxied server-side to the backend. The browser never sees the backend URL.
- Health check routes (`/health/*`) are also proxied.
- Sitemap is a local rewrite, not API-related.

## Cookie Behavior

Since the frontend proxies API requests, cookies set by the backend arrive on the **frontend's domain** (e.g., `web-xxx.vercel.app`). The backend sets:

- `healthcare_session` cookie — the session token
- Cookie attributes depend on `COOKIE_DOMAIN` env var

**`COOKIE_DOMAIN` must be empty** for the Vercel proxy arrangement. An empty domain means the cookie scopes to the exact host that set it — which is the Vercel frontend domain (since the browser talks to Vercel, not Render directly).

If `COOKIE_DOMAIN` is set to the Render domain, cookies won't be sent on subsequent requests to the Vercel frontend. **This is a common misconfiguration.**

## CSRF Behavior

**Source**: CSRF validation happens in `identity/routes.py` via `_validate_origin()`.

The CSRF check compares the `Origin` header against `CSRF_ALLOWED_ORIGINS`. Since the browser sends requests to the Vercel frontend domain, the `Origin` header will be the Vercel URL.

**`CSRF_ALLOWED_ORIGINS` must match the Vercel frontend URL exactly** (e.g., `https://web-eight-flax-pmiw08soee.vercel.app`).

## CORS Behavior

CORS middleware in `main.py:107-114` uses `CORS_ORIGINS` (falls back to `CSRF_ALLOWED_ORIGINS`).

Since API requests go through the Next.js server-side rewrite, the browser never makes cross-origin requests to the backend. **CORS headers are not strictly needed for the primary flow.** However, if any client-side code makes direct API calls (unlikely but possible), CORS must be configured.

**Setting `CORS_ORIGINS` to the Vercel URL is correct and harmless.**

## Integration Checklist

| Check | Status | Evidence |
|-------|--------|---------|
| API_URL reads Render URL | OK if set | `next.config.ts:15` |
| Rewrite proxies /api/* | OK | `next.config.ts:26` |
| Rewrite proxies /health/* | OK | `next.config.ts:27` |
| Cookie domain compatible | OK if empty | Backend respects `COOKIE_DOMAIN` env var |
| CSRF origin matches frontend | OK if set | Backend checks `Origin` header |
| CORS origin matches frontend | OK if set | Fallback to `CSRF_ALLOWED_ORIGINS` |
| No localhost fallback in production | RISK | Default `http://localhost:8000` if API_URL unset |
| Preview deploys need wildcard CORS | SUPPORTED | `origin_allowed()` in config.py:63-75 supports `*` wildcard patterns |

## Staging Integration Strategy

1. **Do NOT update the current Vercel production `API_URL`** until Render is verified.
2. Create a **Vercel preview deployment** or use a branch deploy to test with the Render URL.
3. Verify: login → session cookie set → subsequent requests authenticated → CSRF passes on mutations.
4. Only after verification: update the production `API_URL` on Vercel.

Alternatively, test directly against the Render API using curl:
```bash
# Health check
curl https://healthcare-api-xxxx.onrender.com/health/ready

# Login (verify CSRF/CORS don't block)
curl -X POST https://healthcare-api-xxxx.onrender.com/api/v1/auth/login \
  -H "Origin: https://web-eight-flax-pmiw08soee.vercel.app" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test"}'
```

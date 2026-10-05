import { NextResponse, type NextRequest } from "next/server";

function nonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes));
}

export function proxy(request: NextRequest) {
  const requestNonce = nonce();
  const development = process.env.NODE_ENV === "development";
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", requestNonce);
  // Browser API calls hit `/api/*` on this origin and are rewritten (next.config.ts)
  // to the API behind an ngrok free-tier tunnel, which serves an HTML "browser warning"
  // interstitial (ERR_NGROK_6024) to any browser User-Agent and breaks JSON fetches.
  // The `ngrok-skip-browser-warning` request header (any value) bypasses it; inject it
  // on proxied API requests so the forwarded request reaches the API directly.
  if (request.nextUrl.pathname.startsWith("/api/")) {
    requestHeaders.set("ngrok-skip-browser-warning", "true");
  }
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${requestNonce}'${development ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "connect-src 'self'",
    "font-src 'self'",
    "frame-ancestors 'none'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join("; ");
  requestHeaders.set("Content-Security-Policy", csp);
  response.headers.set("Content-Security-Policy", csp);
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("X-Frame-Options", "DENY");
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  response.headers.set("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
  if (process.env.NODE_ENV === "production") {
    response.headers.set("Strict-Transport-Security", "max-age=31536000; includeSubDomains");
  }
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};

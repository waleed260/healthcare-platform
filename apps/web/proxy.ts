import { NextResponse, type NextRequest } from "next/server";

function nonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes));
}

export function proxy(request: NextRequest) {
  const requestNonce = nonce();
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", requestNonce);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${requestNonce}' 'strict-dynamic'`,
    `style-src 'self' 'nonce-${requestNonce}'`,
    "img-src 'self' data:",
    "connect-src 'self'",
    "font-src 'self'",
    "frame-ancestors 'none'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join("; ");
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

import { cachedFetch, cachedRefData } from "./session-cache";

export type ApiEnvelope<T> = { data?: T; error?: { code?: string; message?: string; fields?: Record<string, string> } };

const SESSION_CACHED = new Set(["/api/v1/auth/me", "/api/v1/clinic/context"]);
const REF_CACHED = new Set(["/api/v1/branches?limit=100", "/api/v1/doctors?limit=100", "/api/v1/services?limit=100"]);

// Single place where auth-expiry sends the user back to login. Preserves the deep
// link as ?next= so the login page can return the user exactly where they were.
// Uses a full navigation on purpose: it also clears in-memory client state left by
// the expired session (caches, toasts, drawers) that router.push would keep alive.
export function redirectToLogin(): void {
  const here = window.location.pathname + window.location.search + window.location.hash;
  const target = here && here !== "/" ? `?next=${encodeURIComponent(here)}` : "";
  window.location.assign(`/login${target}`);
}

// Guard used by the login page: only same-app relative paths may be used as `next`.
export function safeNextPath(value: string | null): string | null {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return null;
  return value;
}

async function refreshCsrf(): Promise<string | undefined> {
  try {
    const r = await fetch("/api/v1/auth/csrf", { method: "POST", credentials: "include" });
    const body = await r.json().catch(() => null) as { data?: { csrf_token?: string } } | null;
    return body?.data?.csrf_token ?? undefined;
  } catch { return undefined; }
}

export async function api<T>(url: string, init?: globalThis.RequestInit, fallback = "The request could not be completed."): Promise<T> {
  const isGet = !init?.method || init.method === "GET";
  if (isGet && SESSION_CACHED.has(url)) return cachedFetch<T>(url, 60_000);
  if (isGet && REF_CACHED.has(url)) return cachedRefData<T>(url);
  const response = await fetch(url, { credentials: "include", ...(isGet ? {} : { cache: "no-store" as const }), ...init });
  const payload = await response.json().catch(() => null) as ApiEnvelope<T> | null;
  if (!response.ok) {
    if (response.status === 401 && payload?.error?.code === "SESSION_EXPIRED") {
      redirectToLogin();
      throw new Error("Session expired — redirecting to login.");
    }
    if ((payload?.error?.code === "CSRF_INVALID" || payload?.error?.code === "CSRF_REQUIRED") && init?.method && init.method !== "GET") {
      const freshToken = await refreshCsrf();
      const token = freshToken ?? csrfToken();
      const h = new Headers(init.headers);
      h.set("X-CSRF-Token", token);
      const retry = await fetch(url, { ...init, headers: h, credentials: "include", cache: "no-store" });
      const retryPayload = await retry.json().catch(() => null) as ApiEnvelope<T> | null;
      if (!retry.ok) {
        if (retry.status === 401) {
          redirectToLogin();
          throw new Error("Session expired — redirecting to login.");
        }
        throw new Error(retryPayload?.error?.message ?? fallback);
      }
      return retryPayload?.data as T;
    }
    const fields = payload?.error?.fields;
    const fieldHint = fields ? ": " + Object.values(fields).slice(0, 2).join(", ") : "";
    throw new Error((payload?.error?.message ?? fallback) + fieldHint);
  }
  return payload?.data as T;
}

export type Page<T> = { data: T[]; nextCursor: string | null };

// Like api(), but keeps meta.next_cursor so callers can page through cursor-paginated lists.
export async function apiPage<T>(url: string, fallback = "The request could not be completed."): Promise<Page<T>> {
  const response = await fetch(url, { credentials: "include", cache: "no-store" });
  const payload = await response.json().catch(() => null) as { data?: T[]; meta?: { next_cursor?: string | null }; error?: { message?: string } } | null;
  if (!response.ok) {
    if (response.status === 401) {
      redirectToLogin();
      throw new Error("Session expired — redirecting to login.");
    }
    throw new Error(payload?.error?.message ?? fallback);
  }
  return { data: Array.isArray(payload?.data) ? (payload!.data as T[]) : [], nextCursor: payload?.meta?.next_cursor ?? null };
}

export function csrfToken(): string {
  const parts = document.cookie.split(";").map((c) => c.trim()).filter((c) => c.startsWith("csrf_token="));
  const last = parts[parts.length - 1];
  return last ? decodeURIComponent(last.slice(11)) : "";
}

export function writeHeaders(): Record<string, string> {
  return { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() };
}

export function post<T>(url: string, body?: unknown, fallback?: string): Promise<T> {
  return api<T>(url, { method: "POST", headers: writeHeaders(), body: body === undefined ? undefined : JSON.stringify(body) }, fallback);
}

export function patch<T>(url: string, body: unknown, fallback?: string): Promise<T> {
  return api<T>(url, { method: "PATCH", headers: writeHeaders(), body: JSON.stringify(body) }, fallback);
}

export const label = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

export const money = (minor: number, currency = "PKR") =>
  new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(minor / 100);

export const errorMessage = (reason: unknown, fallback: string) => (reason instanceof Error ? reason.message : fallback);

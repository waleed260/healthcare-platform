export type ApiEnvelope<T> = { data?: T; error?: { message?: string } };

export async function api<T>(url: string, init?: globalThis.RequestInit, fallback = "The request could not be completed."): Promise<T> {
  const response = await fetch(url, { credentials: "include", cache: "no-store", ...init });
  const payload = await response.json().catch(() => null) as ApiEnvelope<T> | null;
  if (!response.ok) throw new Error(payload?.error?.message ?? fallback);
  return payload?.data as T;
}

export function csrfToken(): string {
  return document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith("csrf_token="))?.slice(11) ?? "";
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

import { redirectToLogin } from "./client";

type CacheEntry<T> = { data: T; ts: number };

const cache = new Map<string, CacheEntry<unknown>>();
const inflight = new Map<string, Promise<unknown>>();

const DEFAULT_TTL = 30_000;

export function cachedFetch<T>(url: string, ttlMs = DEFAULT_TTL): Promise<T> {
  const entry = cache.get(url) as CacheEntry<T> | undefined;
  if (entry && Date.now() - entry.ts < ttlMs) return Promise.resolve(entry.data);

  const pending = inflight.get(url) as Promise<T> | undefined;
  if (pending) return pending;

  const promise = fetch(url, { credentials: "include" })
    .then(async (res) => {
      if (res.status === 401) {
        redirectToLogin();
        throw new Error("Session expired");
      }
      if (!res.ok) throw new Error("Fetch failed");
      const body = (await res.json()) as { data?: T };
      const data = body.data as T;
      // Only cache if this fetch is still the current in-flight one — a
      // mid-flight invalidateCache() drops the entry, and writing here would
      // re-seed the cache with pre-mutation data.
      if (inflight.get(url) === promise) cache.set(url, { data, ts: Date.now() });
      return data;
    })
    .finally(() => {
      if (inflight.get(url) === promise) inflight.delete(url);
    });

  inflight.set(url, promise);
  return promise;
}

export function invalidateCache(url?: string): void {
  if (url) { cache.delete(url); inflight.delete(url); }
  else { cache.clear(); inflight.clear(); }
}

const REF_TTL = 120_000;

export function cachedRefData<T>(url: string): Promise<T> {
  return cachedFetch<T>(url, REF_TTL);
}

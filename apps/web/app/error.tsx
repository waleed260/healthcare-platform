"use client";

import { useEffect } from "react";

// Route-level error boundary. Its most important job: when a new deployment
// replaces the JS chunks a still-open tab was using, a client-side navigation
// throws a ChunkLoadError and the route renders blank. We detect that and
// reload once to pick up the new build (guarded against reload loops).
const CHUNK_RE = /ChunkLoadError|Loading chunk [\d]+ failed|Failed to fetch dynamically imported module|error loading dynamically imported module|importing a module script failed/i;

export default function RouteError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const isChunkError = error?.name === "ChunkLoadError" || CHUNK_RE.test(error?.message ?? "");

  useEffect(() => {
    if (!isChunkError) return;
    // Reload at most once per 12s window so a genuinely broken deploy can't loop.
    try {
      const key = "cf-chunk-reload-at";
      const last = Number(sessionStorage.getItem(key) ?? "0");
      if (Date.now() - last > 12000) {
        sessionStorage.setItem(key, String(Date.now()));
        window.location.reload();
      }
    } catch {
      window.location.reload();
    }
  }, [isChunkError]);

  return <main className="route-error" role="alert">
    <p className="eyebrow">{isChunkError ? "New version available" : "Something went wrong"}</p>
    <h1>{isChunkError ? "Updating to the latest version…" : "This page hit a snag."}</h1>
    <p className="route-error-copy">{isChunkError
      ? "A new release just shipped. We’re reloading to pick it up — if nothing happens, use Reload page below."
      : "You can retry this view, or reload the page. If it keeps happening, sign in again."}</p>
    <div className="route-error-actions">
      <button className="button button-primary" type="button" onClick={() => reset()}>Try again <span>→</span></button>
      <button className="button button-secondary" type="button" onClick={() => window.location.reload()}>Reload page</button>
    </div>
  </main>;
}

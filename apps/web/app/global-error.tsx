"use client";

import { useEffect } from "react";

// Catches errors thrown in the root layout itself. It replaces <html>/<body>,
// so it must render them. Same chunk-error auto-reload as the route boundary.
const CHUNK_RE = /ChunkLoadError|Loading chunk [\d]+ failed|Failed to fetch dynamically imported module|error loading dynamically imported module|importing a module script failed/i;

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const isChunkError = error?.name === "ChunkLoadError" || CHUNK_RE.test(error?.message ?? "");

  useEffect(() => {
    if (!isChunkError) return;
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

  return <html lang="en">
    <body style={{ margin: 0, minHeight: "100vh", display: "grid", placeItems: "center", background: "#f5f4ee", color: "#1c2928", fontFamily: "'DM Sans', system-ui, sans-serif", textAlign: "center", padding: "24px" }}>
      <div style={{ maxWidth: 440 }}>
        <p style={{ fontFamily: "'DM Mono', ui-monospace, monospace", fontSize: 12, letterSpacing: ".12em", color: "#677875", margin: "0 0 14px", textTransform: "uppercase" }}>{isChunkError ? "New version available" : "Something went wrong"}</p>
        <h1 style={{ fontFamily: "Fraunces, Georgia, serif", fontWeight: 500, fontSize: 34, lineHeight: 1.1, margin: "0 0 12px" }}>{isChunkError ? "Updating…" : "The workspace hit a snag."}</h1>
        <p style={{ color: "#677875", fontSize: 15, lineHeight: 1.6, margin: "0 0 24px" }}>{isChunkError ? "A new release just shipped — reloading to pick it up." : "Reload the page to continue. If it keeps happening, sign in again."}</p>
        <button type="button" onClick={() => reset()} style={{ background: "#274c42", color: "#fff", border: 0, padding: "14px 20px", fontSize: 13, cursor: "pointer", borderRadius: 2 }}>Reload page</button>
      </div>
    </body>
  </html>;
}

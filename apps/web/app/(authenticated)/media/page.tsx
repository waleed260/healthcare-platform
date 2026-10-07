"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, errorMessage, label, patch, writeHeaders } from "../_lib/client";
import { useToast } from "../_lib/toast";
import { useConfirm } from "../_lib/confirm";
import Drawer from "../_lib/drawer";

type MediaItem = { id: string; original_filename?: string; alt_text: string; mime_type: string; size_bytes?: number; scan_status: string; is_public: boolean; version: number; created_at: string };
type Session = { permissions?: string[] };

function date(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function fileSize(bytes: number | undefined): string {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

const scanColor: Record<string, string> = { clean: "status-paid", pending_scan: "status-pending", quarantined: "status-lost" };

export default function MediaPage() {
  const [items, setItems] = useState<MediaItem[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [editItem, setEditItem] = useState<MediaItem | null>(null);
  const [altText, setAltText] = useState("");
  const toast = useToast();
  const confirm = useConfirm();
  const can = (p: string) => permissions.includes(p);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [session, mediaData] = await Promise.all([
        api<Session>("/api/v1/auth/me"),
        api<MediaItem[]>("/api/v1/websites/media?limit=100"),
      ]);
      setPermissions(session.permissions ?? []);
      setItems(mediaData ?? []);
    } catch (reason) {
      setError(errorMessage(reason, "Media library could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const filtered = useMemo(() => {
    let result = items;
    if (search) {
      const q = search.toLowerCase();
      result = result.filter((m) => m.alt_text.toLowerCase().includes(q) || (m.original_filename ?? "").toLowerCase().includes(q));
    }
    if (typeFilter !== "all") {
      result = result.filter((m) => m.mime_type === typeFilter);
    }
    return result;
  }, [items, search, typeFilter]);

  const mimeTypes = useMemo(() => {
    const types = new Set(items.map((m) => m.mime_type));
    return Array.from(types).sort();
  }, [items]);

  async function uploadFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const alt = window.prompt("Alt text (required for accessibility)", file.name.replace(/\.[^.]+$/, ""))?.trim();
    if (!alt) { toast.error("Alt text is required."); return; }
    setBusy(true);
    try {
      await api("/api/v1/websites/media/upload", {
        method: "POST",
        headers: { ...writeHeaders(), "Content-Type": file.type, "X-Original-Filename": file.name, "X-Alt-Text": alt },
        body: file,
      });
      toast.success("Image uploaded. It will be scanned before use.");
      await load();
    } catch (reason) {
      toast.error(errorMessage(reason, "The upload failed."));
    } finally {
      setBusy(false);
      event.target.value = "";
    }
  }

  async function updateAltText() {
    if (!editItem) return;
    setBusy(true);
    try {
      await patch(`/api/v1/websites/media/${editItem.id}`, { alt_text: altText.trim(), expected_version: editItem.version });
      toast.success("Alt text updated.");
      setEditItem(null);
      await load();
    } catch (reason) {
      toast.error(errorMessage(reason, "The alt text could not be saved."));
    } finally {
      setBusy(false);
    }
  }

  async function deleteMedia(item: MediaItem) {
    if (item.is_public) { toast.error("Published media cannot be deleted."); return; }
    const ok = await confirm({ title: "Delete media", message: `Delete "${item.alt_text || item.original_filename || "this image"}"? This cannot be undone.`, confirmLabel: "Delete", danger: true });
    if (!ok) return;
    setBusy(true);
    try {
      await api(`/api/v1/websites/media/${item.id}`, { method: "DELETE", headers: writeHeaders(), body: JSON.stringify({ expected_version: item.version }) });
      toast.success("Media deleted.");
      await load();
    } catch (reason) {
      toast.error(errorMessage(reason, "The media could not be deleted."));
    } finally {
      setBusy(false);
    }
  }

  const cleanCount = items.filter((m) => m.scan_status === "clean").length;
  const pendingCount = items.filter((m) => m.scan_status === "pending_scan").length;

  return <main className="workspace-page media-page">
    <div className="workspace-page-header">
      <div>
        <p className="eyebrow">WEBSITE · MEDIA</p>
        <h1>Images that <em>tell your story.</em></h1>
        <p className="workspace-page-intro">Upload, manage, and set alt text for images used on your website. All uploads are scanned before publishing.</p>
      </div>
      <div className="header-actions">
        <button className="button button-secondary" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button>
        {can("website.edit") && <label className="button button-primary" style={{ cursor: "pointer" }}>
          Upload image <span>＋</span>
          <input type="file" accept="image/jpeg,image/png,image/webp" onChange={uploadFile} style={{ display: "none" }} disabled={busy} />
        </label>}
      </div>
    </div>

    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" onClick={() => void load()}>Try again <span>→</span></button></div>}

    <div className="inventory-summary" style={{ marginBottom: 20 }}>
      <div className="inventory-summary-dark"><span className="eyebrow">TOTAL</span><strong>{items.length}</strong><small>media files</small></div>
      <div><span className="eyebrow">READY</span><strong>{cleanCount}</strong><small>passed scan</small></div>
      <div><span className="eyebrow">PENDING</span><strong>{pendingCount}</strong><small>awaiting scan</small></div>
    </div>

    {/* Filters */}
    {items.length > 0 && <div className="pipeline-toolbar" style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <input type="search" placeholder="Search by name or alt text…" value={search} onChange={(e) => setSearch(e.target.value)} style={{ maxWidth: 240, padding: "6px 12px", border: "1px solid var(--border-subtle, #e5e5e3)", borderRadius: 6, fontSize: "0.85rem", background: "var(--surface-1, #fff)" }} />
        <div className="pipeline-tabs" role="tablist" style={{ fontSize: "0.78rem" }}>
          <button role="tab" aria-selected={typeFilter === "all"} className={typeFilter === "all" ? "active" : ""} onClick={() => setTypeFilter("all")}>All</button>
          {mimeTypes.map((t) => <button key={t} role="tab" aria-selected={typeFilter === t} className={typeFilter === t ? "active" : ""} onClick={() => setTypeFilter(t)}>{t.replace("image/", "")}</button>)}
        </div>
      </div>
    </div>}

    {loading && items.length === 0 && <div className="dashboard-empty" role="status"><strong>Loading media library</strong><span>Fetching your uploaded images…</span></div>}

    {/* Media grid */}
    <section className="surface-card">
      <div className="surface-card-heading">
        <div><p className="eyebrow">MEDIA LIBRARY</p><h2>All uploaded images</h2></div>
        <span className="muted-mono">{filtered.length} FILE{filtered.length !== 1 ? "S" : ""}</span>
      </div>
      {!loading && filtered.length === 0 && <div className="dashboard-empty"><strong>{search || typeFilter !== "all" ? "No matching media" : "No media uploaded yet"}</strong><span>Upload images to use them on your website pages.</span></div>}
      {filtered.length > 0 && <div className="invoice-list">
        {filtered.map((item) => <article className="invoice-row" key={item.id}>
          <div className="invoice-mark" style={{ fontSize: "0.7rem", textTransform: "uppercase" }}>{item.mime_type.replace("image/", "").slice(0, 4)}</div>
          <div className="invoice-main">
            <h3>{item.original_filename || item.alt_text || item.id.slice(0, 12)}</h3>
            <p>{item.alt_text || "No alt text"}{item.size_bytes ? ` · ${fileSize(item.size_bytes)}` : ""}</p>
            <small>
              <span className={`pipeline-status ${scanColor[item.scan_status] ?? ""}`}>{label(item.scan_status)}</span>
              {item.is_public ? " · Published" : " · Draft"}
              {" · "}{date(item.created_at)}
            </small>
          </div>
          <div className="invoice-actions" style={{ display: "flex", gap: 6, alignItems: "center" }}>
            {can("website.edit") && !item.is_public && <button className="text-control" disabled={busy} onClick={() => { setEditItem(item); setAltText(item.alt_text); }}>Edit</button>}
            {can("website.edit") && !item.is_public && <button className="text-control" disabled={busy} onClick={() => void deleteMedia(item)}>Delete</button>}
            {item.is_public && <span className="pipeline-status status-paid" style={{ fontSize: "0.72rem" }}>PUBLISHED</span>}
          </div>
        </article>)}
      </div>}
    </section>

    {/* Edit alt text drawer */}
    <Drawer open={!!editItem} onClose={() => setEditItem(null)} title="Edit media" subtitle={editItem?.original_filename ?? editItem?.id}>
      {editItem && <div>
        <div className="form-grid">
          <label>File<input readOnly value={editItem.original_filename || editItem.id} /></label>
          <label>Type<input readOnly value={editItem.mime_type} /></label>
          <label>Scan status<input readOnly value={label(editItem.scan_status)} /></label>
          <label>Alt text<textarea value={altText} onChange={(e) => setAltText(e.target.value)} rows={3} placeholder="Describe the image for screen readers" /></label>
        </div>
        <div className="form-actions" style={{ marginTop: 16 }}>
          <button className="button button-primary" disabled={busy || !altText.trim() || altText.trim() === editItem.alt_text} onClick={() => void updateAltText()}>{busy ? "Saving…" : "Save alt text"}</button>
        </div>
      </div>}
    </Drawer>
  </main>;
}

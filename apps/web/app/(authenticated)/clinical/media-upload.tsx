"use client";

import { useRef, useState } from "react";
import { csrfToken, errorMessage } from "../_lib/client";

type Item = { name: string; status: "uploading" | "done" | "error"; detail?: string };
const KINDS = ["before", "after", "other"] as const;
const ACCEPT = "image/jpeg,image/png,image/webp";

type Done = () => void;

export default function MediaUpload({ patientId, onUploaded }: { patientId: string; onUploaded: Done }) {
  const [kind, setKind] = useState<(typeof KINDS)[number]>("before");
  const [items, setItems] = useState<Item[]>([]);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function uploadOne(file: File): Promise<Item> {
    try {
      const response = await fetch(`/api/v1/patients/${patientId}/media/upload?media_kind=${kind}`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": file.type || "application/octet-stream", "X-CSRF-Token": csrfToken() },
        body: file,
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null) as { error?: { message?: string } } | null;
        return { name: file.name, status: "error", detail: payload?.error?.message ?? `HTTP ${response.status}` };
      }
      return { name: file.name, status: "done", detail: "pending scan" };
    } catch (reason) {
      return { name: file.name, status: "error", detail: errorMessage(reason, "upload failed") };
    }
  }

  async function onFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    const chosen = Array.from(files).slice(0, 20);
    setBusy(true);
    setItems(chosen.map((f) => ({ name: f.name, status: "uploading" as const })));
    const results: Item[] = [];
    for (const file of chosen) {
      const result = await uploadOne(file);
      results.push(result);
      setItems((current) => current.map((it) => (it.name === result.name ? result : it)));
    }
    setBusy(false);
    if (inputRef.current) inputRef.current.value = "";
    if (results.some((r) => r.status === "done")) onUploaded();
  }

  return <div className="media-upload">
    <div className="form-grid">
      <label>Media type<select value={kind} onChange={(e) => setKind(e.target.value as (typeof KINDS)[number])} disabled={busy}>{KINDS.map((k) => <option key={k} value={k}>{k}</option>)}</select></label>
      <label>Upload photos<input ref={inputRef} type="file" accept={ACCEPT} multiple disabled={busy} onChange={(e) => void onFiles(e.target.files)} /></label>
    </div>
    {items.length > 0 && <ul className="media-upload-list">{items.map((it) => <li key={it.name} className={`media-upload-${it.status}`}><span>{it.name}</span><small>{it.status === "uploading" ? "uploading…" : it.detail}</small></li>)}</ul>}
    <p className="field-note">JPEG, PNG or WebP up to 8 MiB. Uploads are scanned before they can be approved for the website.</p>
  </div>;
}

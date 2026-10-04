"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, errorMessage, post, patch } from "../_lib/client";

type SiteTemplate = { key: string; name: string; specialty: string; description: string; page_count: number; locked: boolean };
type PageTemplate = { key: string; name: string; description: string; section_count: number };
type Library = { site_templates: SiteTemplate[]; page_templates: PageTemplate[] };
type Reusable = { id: string; name: string; section_type: string; version: number; synced_uses: number; content: { heading?: string } };
type SectionRef = { id: string; section_type: string; content: { heading?: string } };

type Props = {
  website: { id: string; version: number };
  pageId: string | null;
  sections: SectionRef[];
  disabled: boolean;
  onChanged: () => void;
};

export default function LibraryPanel({ website, pageId, sections, disabled, onChanged }: Props) {
  const [library, setLibrary] = useState<Library | null>(null);
  const [reusable, setReusable] = useState<Reusable[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [sourceId, setSourceId] = useState("");

  const load = useCallback(async () => {
    try {
      const [lib, rows] = await Promise.all([api<Library>("/api/v1/website-library/templates"), api<Reusable[]>("/api/v1/website-library/reusable-sections")]);
      setLibrary(lib && !Array.isArray(lib) ? lib : null);
      setReusable(Array.isArray(rows) ? rows : []);
    } catch (reason) {
      setError(errorMessage(reason, "The template library could not be loaded."));
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function run(key: string, action: () => Promise<unknown>, success: string) {
    setBusy(key); setError(null); setNotice(null);
    try { await action(); setNotice(success); await load(); onChanged(); } catch (reason) { setError(errorMessage(reason, "That action could not be completed.")); } finally { setBusy(null); }
  }

  const applySite = (template: SiteTemplate) => {
    if (!window.confirm(`Apply “${template.name}”? Theme, header and footer are replaced; existing pages are kept and missing pages are added.`)) return;
    void run(template.key, () => post(`/api/v1/website-library/websites/${website.id}/apply-site-template`, { template_key: template.key, expected_version: website.version }), `${template.name} applied to the draft.`);
  };
  const addPage = (event: FormEvent<HTMLFormElement>, template: PageTemplate) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const title = String(form.get("title")).trim();
    const slug = String(form.get("slug")).trim().toLowerCase();
    void run(template.key, () => post(`/api/v1/website-library/websites/${website.id}/pages-from-template`, { template_key: template.key, slug, title }), `Page “${title}” created.`);
  };
  const saveReusable = (event: FormEvent) => {
    event.preventDefault();
    void run("reusable-create", () => post("/api/v1/website-library/reusable-sections", { name: newName.trim(), source_section_id: sourceId }), "Reusable section saved.").then(() => setNewName(""));
  };
  const insert = (item: Reusable, mode: "copy" | "synced") => {
    if (!pageId) return;
    void run(`${item.id}-${mode}`, () => post(`/api/v1/website-library/websites/${website.id}/pages/${pageId}/insert-reusable/${item.id}`, { mode }), mode === "synced" ? "Inserted as a synced section." : "Inserted as an independent copy.");
  };
  const rename = (item: Reusable) => {
    const name = window.prompt("New name", item.name)?.trim();
    if (name && name !== item.name) void run(item.id, () => patch(`/api/v1/website-library/reusable-sections/${item.id}`, { expected_version: item.version, name }), "Renamed.");
  };
  const removeReusable = (item: Reusable) => {
    if (window.confirm(`Delete “${item.name}”? ${item.synced_uses} synced use(s) become independent copies.`)) void run(item.id, () => api(`/api/v1/website-library/reusable-sections/${item.id}`, { method: "DELETE", headers: { "X-CSRF-Token": document.cookie.split(";").map((p) => p.trim()).find((p) => p.startsWith("csrf_token="))?.slice(11) ?? "" } }), "Deleted.");
  };

  return <section className="detail-card library-panel" aria-label="Templates and reusable sections">
    <div className="card-heading"><div><p className="eyebrow">Library</p><h2>Start fast, stay consistent</h2></div></div>
    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong></div>}
    {notice && <div className="permission-strip" aria-live="polite"><span className="permission-ok">{notice}</span></div>}

    <p className="eyebrow">Site templates</p>
    <div className="library-grid">{library?.site_templates?.map((template) => <article className="library-card" key={template.key}><h3>{template.name}</h3><p>{template.description}</p><small>{template.page_count} pages · {template.specialty}</small>{template.locked ? <span className="pipeline-status status-void" title="Specialty locked">Locked</span> : <button className="button button-secondary" disabled={disabled || busy !== null} onClick={() => applySite(template)}>{busy === template.key ? "Applying…" : "Apply template"}</button>}</article>)}</div>

    <p className="eyebrow">Page templates</p>
    <div className="library-grid">{library?.page_templates?.map((template) => <form className="library-card" key={template.key} onSubmit={(event) => addPage(event, template)}><h3>{template.name}</h3><p>{template.description}</p><input name="title" required maxLength={160} placeholder="Page title" disabled={disabled} /><input name="slug" required maxLength={120} pattern="[a-z0-9][a-z0-9_\-]*" placeholder="url-slug" disabled={disabled} /><button className="button button-secondary" type="submit" disabled={disabled || busy !== null}>Create page</button></form>)}</div>

    <p className="eyebrow">Reusable sections</p>
    <form className="theme-row" onSubmit={saveReusable}><select aria-label="Section to save" value={sourceId} onChange={(event) => setSourceId(event.target.value)} required disabled={disabled}><option value="">Choose a section on this page…</option>{sections.map((section) => <option key={section.id} value={section.id}>{section.section_type} · {section.content.heading ?? ""}</option>)}</select><input aria-label="Reusable name" value={newName} onChange={(event) => setNewName(event.target.value)} required maxLength={120} placeholder="Name, e.g. Booking banner" disabled={disabled} /><button className="button button-primary" type="submit" disabled={disabled || busy !== null || !sourceId}>Save for reuse</button></form>
    <div className="invoice-list">{reusable.length === 0 && <div className="dashboard-empty"><strong>No reusable sections yet</strong><span>Save a section above to reuse it on other pages.</span></div>}{reusable.map((item) => <article className="invoice-row" key={item.id}><div className="invoice-mark">{item.section_type.slice(0, 3).toUpperCase()}</div><div className="invoice-main"><h3>{item.name}</h3><p>{item.content.heading ?? item.section_type}</p><small>{item.synced_uses} synced use(s)</small></div><div className="invoice-actions"><span className="receipt-links"><button className="text-control" disabled={disabled || !pageId || busy !== null} onClick={() => insert(item, "copy")}>Insert copy</button><button className="text-control" disabled={disabled || !pageId || busy !== null} onClick={() => insert(item, "synced")}>Insert synced</button></span><span className="receipt-links"><button className="text-control" disabled={disabled} onClick={() => rename(item)}>Rename</button><button className="text-control" disabled={disabled} onClick={() => removeReusable(item)}>Delete</button></span></div></article>)}</div>
  </section>;
}

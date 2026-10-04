"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, errorMessage, patch, post } from "../_lib/client";
import type { SeoSettings, SiteBrand } from "../../site-theme";

type PageRow = { id: string; slug: string; title: string; seo_title: string | null; seo_description: string | null; canonical_url: string | null; noindex: boolean; og_title: string | null; og_description: string | null; version: number };
type RedirectRow = { id: string; from_path: string; to_path: string; status_code: number };

// eslint-disable-next-line no-unused-vars
type SaveSeo = (seo: SeoSettings) => Promise<void>;

export default function SeoPanel({ website, disabled, onSaveSeo }: { website: { id: string; brand?: SiteBrand }; disabled: boolean; onSaveSeo: SaveSeo }) {
  const [pages, setPages] = useState<PageRow[]>([]);
  const [redirects, setRedirects] = useState<RedirectRow[]>([]);
  const [pageId, setPageId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const seo = website.brand?.seo ?? {};

  const load = useCallback(async () => {
    try {
      const [pageRows, redirectRows] = await Promise.all([api<PageRow[]>(`/api/v1/websites/${website.id}/pages?limit=100`), api<RedirectRow[]>(`/api/v1/websites/${website.id}/redirects`)]);
      setPages(Array.isArray(pageRows) ? pageRows : []);
      setRedirects(Array.isArray(redirectRows) ? redirectRows : []);
      setPageId((current) => current || pageRows?.[0]?.id || "");
    } catch (reason) {
      setError(errorMessage(reason, "SEO settings could not be loaded."));
    }
  }, [website.id]);
  useEffect(() => { void load(); }, [load]);

  const page = pages.find((item) => item.id === pageId);
  const run = async (action: () => Promise<unknown>, success: string) => {
    setBusy(true); setError(null); setNotice(null);
    try { await action(); setNotice(success); await load(); } catch (reason) { setError(errorMessage(reason, "That change could not be saved.")); } finally { setBusy(false); }
  };

  const savePage = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!page) return;
    const form = new FormData(event.currentTarget);
    const value = (key: string) => String(form.get(key) ?? "").trim() || null;
    void run(() => patch(`/api/v1/websites/${website.id}/pages/${page.id}`, { expected_version: page.version, seo_title: value("seo_title"), seo_description: value("seo_description"), canonical_url: value("canonical_url") ?? "", og_title: value("og_title"), og_description: value("og_description"), noindex: form.get("noindex") === "on" }), "Page SEO saved to the draft.");
  };
  const addRedirect = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const target = event.currentTarget;
    const form = new FormData(target);
    void run(async () => { await post(`/api/v1/websites/${website.id}/redirects`, { from_path: String(form.get("from")).trim(), to_path: String(form.get("to")).trim(), status_code: Number(form.get("code")) }); target.reset(); }, "Redirect added.");
  };
  const removeRedirect = (id: string) => void run(() => api(`/api/v1/websites/${website.id}/redirects/${id}`, { method: "DELETE", headers: { "X-CSRF-Token": document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith("csrf_token="))?.slice(11) ?? "" } }), "Redirect removed.");

  return <section className="detail-card seo-panel" aria-label="SEO, sitemap and redirects">
    <div className="card-heading"><div><p className="eyebrow">SEO</p><h2>Be found</h2></div></div>
    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong></div>}
    {notice && <div className="permission-strip" aria-live="polite"><span className="permission-ok">{notice}</span></div>}

    <fieldset className="theme-group" disabled={disabled || busy}><legend>Site-wide</legend><div className="brand-fields">
      <label>Allow search engines<input type="checkbox" checked={seo.robots_index ?? true} onChange={(event) => void run(() => onSaveSeo({ ...seo, robots_index: event.target.checked }), "Indexing preference saved.")} /></label>
      <label>Site name<input maxLength={120} defaultValue={seo.site_name ?? ""} onBlur={(event) => { const next = event.target.value.trim() || null; if (next !== (seo.site_name ?? null)) void run(() => onSaveSeo({ ...seo, site_name: next }), "Site name saved."); }} /></label>
    </div><p className="field-note">Published sites expose <code>/your-clinic/sitemap.xml</code> and <code>/your-clinic/robots.txt</code> automatically.</p></fieldset>

    <fieldset className="theme-group" disabled={disabled || busy}><legend>Page settings</legend>
      <label className="font-field">Page<select value={pageId} onChange={(event) => setPageId(event.target.value)}>{pages.map((item) => <option key={item.id} value={item.id}>{item.title} (/{item.slug})</option>)}</select></label>
      {page && <form key={page.id + page.version} onSubmit={savePage} className="manage-form"><div className="form-grid">
        <label>SEO title<input name="seo_title" maxLength={160} defaultValue={page.seo_title ?? ""} /></label>
        <label>Meta description<input name="seo_description" maxLength={320} defaultValue={page.seo_description ?? ""} /></label>
        <label>Canonical URL<input name="canonical_url" maxLength={500} defaultValue={page.canonical_url ?? ""} placeholder="https://… or /path" /></label>
        <label>Social title<input name="og_title" maxLength={160} defaultValue={page.og_title ?? ""} /></label>
        <label>Social description<input name="og_description" maxLength={320} defaultValue={page.og_description ?? ""} /></label>
        <label>Hide from search (noindex)<input name="noindex" type="checkbox" defaultChecked={page.noindex} /></label>
      </div><div className="form-actions"><button className="button button-primary" type="submit" disabled={busy}>Save page SEO</button></div></form>}
    </fieldset>

    <fieldset className="theme-group" disabled={disabled || busy}><legend>Redirects</legend>
      <form className="theme-row" onSubmit={addRedirect}><input name="from" required placeholder="/old-page" aria-label="From path" pattern="/[A-Za-z0-9\-._~/]*" /><input name="to" required placeholder="/new-page or https://…" aria-label="To" /><select name="code" defaultValue="301" aria-label="Type"><option value="301">301 permanent</option><option value="302">302 temporary</option></select><button className="button button-secondary" type="submit">Add redirect</button></form>
      {redirects.length === 0 ? <p className="field-note">No redirects yet.</p> : redirects.map((item) => <div className="theme-row" key={item.id}><code>{item.from_path}</code><span>→</span><code>{item.to_path}</code><span className="muted-mono">{item.status_code}</span><button className="text-control" onClick={() => removeRedirect(item.id)}>Remove</button></div>)}
    </fieldset>
  </section>;
}

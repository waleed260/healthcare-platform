"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

type Website = { id: string; name: string; template_key: string; status: string; version: number; draft_version_id?: string | null; live_version_id?: string | null };
type Page = { id: string; slug: string; title: string; seo_title?: string | null; seo_description?: string | null; version: number };
type Section = { id: string; section_type: string; layout_key: string; position: number; content: { heading: string; body: string; button_label?: string | null; button_href?: string | null }; is_visible: boolean; version: number };
type Version = { id: string; version_number: number; published_at?: string | null; created_at: string };

function csrf(): string {
  return document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith("csrf_token="))?.slice("csrf_token=".length) ?? "";
}

type RequestOptions = { method?: string; headers?: Record<string, string>; body?: string };

async function request<T>(url: string, init?: RequestOptions): Promise<T> {
  const response = await fetch(url, { credentials: "include", cache: "no-store", ...init });
  const payload = await response.json().catch(() => null) as { data?: T; error?: { message?: string } } | null;
  if (!response.ok) throw new Error(payload?.error?.message ?? "The website workspace could not be loaded.");
  return payload?.data as T;
}

function writeHeaders(): Record<string, string> {
  return { "Content-Type": "application/json", "X-CSRF-Token": csrf() };
}

export default function WebsiteEditorPage() {
  const [websites, setWebsites] = useState<Website[]>([]);
  const [website, setWebsite] = useState<Website | null>(null);
  const [pages, setPages] = useState<Page[]>([]);
  const [page, setPage] = useState<Page | null>(null);
  const [sections, setSections] = useState<Section[]>([]);
  const [versions, setVersions] = useState<Version[]>([]);
  const [newWebsiteName, setNewWebsiteName] = useState("Synthetic Clinic Website");
  const [newPageTitle, setNewPageTitle] = useState("Home");
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadWebsite = useCallback(async (selected: Website) => {
    setBusy("load"); setError(null); setWebsite(selected);
    try {
      const [pageRows, versionRows] = await Promise.all([
        request<Page[]>(`/api/v1/websites/${selected.id}/pages`),
        request<Version[]>(`/api/v1/websites/${selected.id}/versions`),
      ]);
      setPages(pageRows ?? []); setVersions(versionRows ?? []);
      const firstPage = (pageRows ?? [])[0] ?? null;
      setPage(firstPage);
      setSections(firstPage ? (await request<Section[]>(`/api/v1/websites/${selected.id}/pages/${firstPage.id}/sections`)) ?? [] : []);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The website could not be loaded."); }
    finally { setBusy(null); setLoading(false); }
  }, []);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const rows = await request<Website[]>("/api/v1/websites");
      setWebsites(rows ?? []);
      if ((rows ?? [])[0]) await loadWebsite(rows[0]);
      else setLoading(false);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The website workspace could not be loaded."); setLoading(false); }
  }, [loadWebsite]);

  useEffect(() => { void load(); }, [load]);

  async function createWebsite(event: FormEvent) {
    event.preventDefault(); setBusy("create-website"); setError(null);
    try {
      const created = await request<Website>("/api/v1/websites", { method: "POST", headers: writeHeaders(), body: JSON.stringify({ name: newWebsiteName, template_key: "calm_clinic", brand: {} }) });
      setWebsites((current) => [created, ...current]); await loadWebsite(created);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The website could not be created."); }
    finally { setBusy(null); }
  }

  async function createPage(event: FormEvent) {
    event.preventDefault(); if (!website) return; setBusy("create-page"); setError(null);
    try {
      const created = await request<Page>(`/api/v1/websites/${website.id}/pages`, { method: "POST", headers: writeHeaders(), body: JSON.stringify({ slug: newPageTitle.trim().toLowerCase().replaceAll(" ", "-"), title: newPageTitle }) });
      setPages((current) => [...current, created]); setPage(created); setSections([]);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The page could not be created."); }
    finally { setBusy(null); }
  }

  async function choosePage(next: Page) {
    if (!website) return; setPage(next); setBusy("load-page"); setError(null);
    try { setSections((await request<Section[]>(`/api/v1/websites/${website.id}/pages/${next.id}/sections`)) ?? []); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The page sections could not be loaded."); }
    finally { setBusy(null); }
  }

  async function saveSection(section: Section) {
    if (!website || !page) return; setBusy(section.id); setError(null);
    try {
      const updated = await request<Section>(`/api/v1/websites/${website.id}/pages/${page.id}/sections/${section.id}`, { method: "PATCH", headers: writeHeaders(), body: JSON.stringify({ section_type: section.section_type, layout_key: section.layout_key, position: section.position, content: section.content, is_visible: section.is_visible, expected_version: section.version }) });
      setSections((current) => current.map((item) => item.id === section.id ? updated : item));
      setNotice("Draft saved. The live website is unchanged until publish.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The section could not be saved."); }
    finally { setBusy(null); }
  }

  async function addSection() {
    if (!website || !page) return; setBusy("add-section"); setError(null);
    try {
      const created = await request<Section>(`/api/v1/websites/${website.id}/pages/${page.id}/sections`, { method: "POST", headers: writeHeaders(), body: JSON.stringify({ section_type: "about", layout_key: "text", position: sections.length, content: { heading: "About this clinic", body: "A calm place for thoughtful care.", button_label: null, button_href: null }, is_visible: true }) });
      setSections((current) => [...current, created]);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The section could not be added."); }
    finally { setBusy(null); }
  }

  async function publish() {
    if (!website) return; setBusy("publish"); setError(null);
    try { const updated = await request<Website>(`/api/v1/websites/${website.id}/publish`, { method: "POST", headers: writeHeaders(), body: JSON.stringify({ expected_version: website.version }) }); setWebsite(updated); setWebsites((current) => current.map((item) => item.id === updated.id ? updated : item)); setNotice("Draft published after the server-side safety checks passed."); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The draft could not be published."); }
    finally { setBusy(null); }
  }

  async function rollback(version: Version) {
    if (!website || !window.confirm(`Roll back to version ${version.version_number}?`)) return; setBusy("rollback"); setError(null);
    try { const updated = await request<Website>(`/api/v1/websites/${website.id}/rollback`, { method: "POST", headers: writeHeaders(), body: JSON.stringify({ source_version_id: version.id, expected_version: website.version }) }); setWebsite(updated); setNotice(`Rolled back to version ${version.version_number}.`); await loadWebsite(updated); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The website could not be rolled back."); }
    finally { setBusy(null); }
  }

  return <main className="dashboard-page"><header className="dash-header shell"><Link className="wordmark" href="/">care<span>/</span>fully</Link><div className="clinic-chip" aria-label="Clinic website workspace">Website editor</div></header><div className="dashboard shell"><aside className="sidebar"><p className="eyebrow">WORKSPACE</p><nav aria-label="Workspace navigation"><Link className="side-link" href="/dashboard">◈ <span>Overview</span></Link><Link className="side-link active" href="/website" aria-current="page">✦ <span>Website</span></Link><Link className="side-link" href="/schedule">◷ <span>Schedule</span></Link><Link className="side-link" href="/patients">○ <span>Patients</span></Link></nav></aside><section className="dash-content website-content" aria-busy={loading || busy !== null}><div className="dash-topline"><div><p className="eyebrow">WEBSITE · DRAFT WORKSPACE</p><h1>Shape your <em>front door.</em></h1></div><button className="button button-primary" type="button" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button></div>{error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" type="button" onClick={() => { setError(null); void load(); }}>Try again <span>→</span></button></div>}{notice && <div className="website-notice" role="status">{notice}<button className="ghost-button" type="button" onClick={() => setNotice(null)}>Dismiss</button></div>}{!loading && !website && <form className="setup-card website-create" onSubmit={createWebsite}><p className="eyebrow">START WITH A TEMPLATE</p><h2>Create a clinic website</h2><p className="setup-card-copy">Choose a controlled template. Your first changes remain in draft until you publish them.</p><label htmlFor="website-name">Website name</label><input id="website-name" value={newWebsiteName} onChange={(event) => setNewWebsiteName(event.target.value)} required /><button className="button button-primary" type="submit" disabled={busy !== null}>Create draft <span>→</span></button></form>}{website && <><div className="website-toolbar"><label>Website<select value={website.id} onChange={(event) => { const next = websites.find((item) => item.id === event.target.value); if (next) void loadWebsite(next); }}>{websites.map((item) => <option value={item.id} key={item.id}>{item.name} · {item.template_key}</option>)}</select></label><span className="draft-status">{website.status} · version {website.version}</span><button className="button button-primary" type="button" onClick={() => void publish()} disabled={busy !== null}>Publish draft <span>↑</span></button></div><div className="editor-grid"><section className="detail-card"><div className="card-heading"><div><p className="eyebrow">PAGES</p><h2>Site structure</h2></div><span className="directory-count">{pages.length} pages</span></div>{pages.length === 0 ? <form className="setup-card" onSubmit={createPage}><label htmlFor="page-title">First page title</label><input id="page-title" value={newPageTitle} onChange={(event) => setNewPageTitle(event.target.value)} required /><button className="button button-secondary" type="submit" disabled={busy !== null}>Add page <span>→</span></button></form> : <div className="page-list">{pages.map((item) => <button className={page?.id === item.id ? "page-choice active" : "page-choice"} type="button" onClick={() => void choosePage(item)} key={item.id}><span>{item.title}</span><small>/{item.slug}</small></button>)}</div>}</section><section className="detail-card editor-sections"><div className="card-heading"><div><p className="eyebrow">DRAFT CONTENT</p><h2>{page?.title ?? "Choose a page"}</h2></div><button className="button button-secondary" type="button" onClick={() => void addSection()} disabled={!page || busy !== null}>Add section <span>＋</span></button></div>{page && sections.length === 0 && <div className="dashboard-empty"><strong>This page is empty</strong><span>Add a controlled section to begin editing.</span></div>}{sections.map((section) => <article className="editor-section" key={section.id}><label>Heading<input value={section.content.heading} onChange={(event) => setSections((current) => current.map((item) => item.id === section.id ? { ...item, content: { ...item.content, heading: event.target.value } } : item))} /></label><label>Body<textarea rows={4} value={section.content.body} onChange={(event) => setSections((current) => current.map((item) => item.id === section.id ? { ...item, content: { ...item.content, body: event.target.value } } : item))} /></label><div className="editor-section-actions"><span className="directory-count">{section.section_type} · draft v{section.version}</span><button className="button button-secondary" type="button" onClick={() => void saveSection(section)} disabled={busy !== null}>Save section <span>✓</span></button></div></article>)}</section></div><section className="detail-card version-card"><div className="card-heading"><div><p className="eyebrow">VERSION HISTORY</p><h2>Safe rollback</h2></div><span className="directory-count">{versions.length} versions</span></div>{versions.length === 0 ? <p className="privacy-caption">Publish a draft to create an immutable version.</p> : <div className="version-list">{versions.map((version) => <div className="version-row" key={version.id}><span>Version {version.version_number}{version.published_at ? " · live" : " · draft"}</span><button className="ghost-button" type="button" onClick={() => void rollback(version)} disabled={busy !== null}>Roll back</button></div>)}</div>}</section></>}</section></div></main>;
}

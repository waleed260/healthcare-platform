"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, CSSProperties, FormEvent } from "react";
import ThemePanel from "./theme-panel";
import LibraryPanel from "./library-panel";
import SeoPanel from "./seo-panel";
import { SiteHeader, SiteFooter } from "../../[clinicSlug]/site-chrome";
import { themeStyle, buttonClass } from "../../site-theme";
import type { SiteBrand } from "../../site-theme";
import { api, csrfToken } from "../_lib/client";

/* ────────────────────────────────────────────────────
   Types
   ──────────────────────────────────────────────────── */
type Brand = SiteBrand;
type Website = { id: string; name: string; template_key: string; status: string; version: number; brand?: Brand; draft_version_id?: string | null; live_version_id?: string | null };
type Page = { id: string; slug: string; title: string; version: number; seo_title?: string | null; seo_description?: string | null };
type Content = { heading: string; body: string; eyebrow?: string; button_label?: string | null; button_href?: string | null; items?: Array<Record<string, unknown>>; location?: string; address?: string };
type Section = { id: string; section_type: string; layout_key: string; position: number; content: Content; is_visible: boolean; version: number };
type Version = { id: string; version_number: number; published_at?: string | null; created_at: string };
type Domain = { hostname: string; observed_status: string };
type Validation = { valid: boolean; code: string | null; message: string | null };
type Session = { permissions?: string[]; clinic_slug?: string | null };
type RequestOptions = { method?: string; headers?: Record<string, string>; body?: string | Blob | null };

/* ────────────────────────────────────────────────────
   Constants
   ──────────────────────────────────────────────────── */
type TemplateKey = "calm_clinic" | "editorial_practice" | "warm_studio";
const templates: Array<{ key: TemplateKey; label: string; description: string }> = [
  { key: "calm_clinic", label: "Calm Clinic", description: "Quiet, considered, and welcoming." },
  { key: "editorial_practice", label: "Editorial Practice", description: "Precise, typographic, and confident." },
  { key: "warm_studio", label: "Warm Studio", description: "Friendly, tactile, and optimistic." },
];
function templateKey(value?: string): TemplateKey { return value === "editorial_practice" || value === "warm_studio" ? value : "calm_clinic"; }
function templateLabel(value?: string) { return templates.find((t) => t.key === templateKey(value))?.label ?? "Calm Clinic"; }

type ThemePreset = { key: string; name: string; blurb: string; swatch: [string, string, string]; brand: Partial<Brand> };
const themePresets: ThemePreset[] = [
  { key: "calm_sage", name: "Calm Sage", blurb: "Quiet green & cream", swatch: ["#274c42", "#e77b5c", "#f5f4ee"], brand: { font_pairing: "dm-sans-fraunces", theme: { colors: { primary: "#274c42", accent: "#e77b5c", text: "#1c2928", background: "#f5f4ee" } } } },
  { key: "editorial_ink", name: "Editorial Ink", blurb: "Confident monochrome", swatch: ["#1c2320", "#b07a4a", "#faf8f3"], brand: { font_pairing: "dm-sans-fraunces", theme: { colors: { primary: "#1c2320", accent: "#b07a4a", text: "#1c2320", background: "#faf8f3" } } } },
  { key: "warm_clay", name: "Warm Clay", blurb: "Friendly terracotta", swatch: ["#a9512f", "#2f6b5e", "#fbf3ec"], brand: { font_pairing: "dm-sans-fraunces", theme: { colors: { primary: "#a9512f", accent: "#2f6b5e", text: "#2a1d17", background: "#fbf3ec" } } } },
  { key: "ocean", name: "Ocean Clinic", blurb: "Deep teal & amber", swatch: ["#13424a", "#e0a458", "#f1f6f6"], brand: { font_pairing: "dm-sans-fraunces", theme: { colors: { primary: "#13424a", accent: "#e0a458", text: "#152a2d", background: "#f1f6f6" } } } },
  { key: "rose_studio", name: "Rose Studio", blurb: "Soft rose & teal", swatch: ["#8d4a5c", "#3f7d74", "#fbf2f3"], brand: { font_pairing: "dm-sans-fraunces", theme: { colors: { primary: "#8d4a5c", accent: "#3f7d74", text: "#301d23", background: "#fbf2f3" } } } },
  { key: "midnight", name: "Midnight", blurb: "Navy & warm gold", swatch: ["#1b2440", "#d8a657", "#f4f3f0"], brand: { font_pairing: "dm-sans-fraunces", theme: { colors: { primary: "#1b2440", accent: "#d8a657", text: "#171d33", background: "#f4f3f0" } } } },
];

type SectionCategory = { label: string; icon: string; types: Array<{ type: string; layout: string; label: string; description: string }> };
const SECTION_LIBRARY: SectionCategory[] = [
  { label: "Hero", icon: "◆", types: [
    { type: "hero", layout: "split", label: "Split hero", description: "Headline left, art right" },
    { type: "hero", layout: "image", label: "Image hero", description: "Full-width background image" },
    { type: "hero", layout: "video", label: "Video hero", description: "Background video header" },
    { type: "hero", layout: "doctor", label: "Doctor hero", description: "Doctor profile hero" },
    { type: "hero", layout: "booking", label: "Booking hero", description: "Hero with booking form" },
  ]},
  { label: "Services", icon: "◈", types: [
    { type: "services", layout: "cards", label: "Service cards", description: "Grid of service cards" },
    { type: "services", layout: "grid", label: "Service grid", description: "Compact service grid" },
    { type: "services", layout: "slider", label: "Service slider", description: "Horizontal scrolling services" },
    { type: "services", layout: "featured", label: "Featured services", description: "Highlighted key services" },
    { type: "pricing", layout: "cards", label: "Pricing table", description: "Service pricing overview" },
  ]},
  { label: "Doctors", icon: "◉", types: [
    { type: "doctor_profile", layout: "grid", label: "Doctor grid", description: "Team member cards" },
    { type: "doctor_profile", layout: "featured", label: "Featured doctor", description: "Spotlight a provider" },
    { type: "doctor_profile", layout: "carousel", label: "Doctor carousel", description: "Sliding doctor cards" },
    { type: "doctor_profile", layout: "team", label: "Team section", description: "Full team layout" },
  ]},
  { label: "Results", icon: "◐", types: [
    { type: "results", layout: "slider", label: "Before/after slider", description: "Side-by-side comparison" },
    { type: "results", layout: "gallery", label: "Case gallery", description: "Grid of approved results" },
    { type: "results", layout: "cases", label: "Treatment results", description: "Case study cards" },
  ]},
  { label: "Social proof", icon: "★", types: [
    { type: "testimonials", layout: "cards", label: "Testimonials", description: "Patient review cards" },
    { type: "testimonials", layout: "reviews", label: "Reviews", description: "Star-rated reviews" },
    { type: "statistics", layout: "cards", label: "Statistics", description: "Key numbers and metrics" },
  ]},
  { label: "Conversion", icon: "→", types: [
    { type: "appointment_cta", layout: "banner", label: "Book appointment", description: "Booking call to action" },
    { type: "appointment_cta", layout: "call", label: "Call CTA", description: "Phone call prompt" },
    { type: "lead_form", layout: "text", label: "Lead form", description: "Contact / enquiry form" },
    { type: "appointment_cta", layout: "consultation", label: "Consultation CTA", description: "Free consultation prompt" },
  ]},
  { label: "Content", icon: "≡", types: [
    { type: "about", layout: "text", label: "Text", description: "Rich text content block" },
    { type: "about", layout: "image_text", label: "Image + text", description: "Side-by-side image and copy" },
    { type: "about", layout: "video", label: "Video", description: "Embedded video section" },
    { type: "about", layout: "timeline", label: "Timeline", description: "Step-by-step process" },
    { type: "about", layout: "comparison", label: "Comparison", description: "Feature comparison table" },
    { type: "faq", layout: "accordion", label: "FAQ", description: "Collapsible questions" },
    { type: "hours", layout: "text", label: "Hours", description: "Operating hours" },
    { type: "location", layout: "map", label: "Map / location", description: "Clinic location" },
    { type: "contact", layout: "text", label: "Contact", description: "Contact information" },
    { type: "legal", layout: "text", label: "Legal", description: "Legal / policy content" },
  ]},
];

const defaultContent: Content = { heading: "", body: "", button_label: null, button_href: null };

type Device = "desktop" | "tablet" | "mobile";
const DEVICE_WIDTH: Record<Device, number | null> = { desktop: null, tablet: 768, mobile: 375 };

type RightTab = "design" | "content" | "page" | "seo" | "library" | "history";

/* ────────────────────────────────────────────────────
   Helpers
   ──────────────────────────────────────────────────── */
async function request<T>(url: string, init?: RequestOptions): Promise<T> {
  return api<T>(url, init);
}
function writeHeaders(extra?: Record<string, string>) { return { "Content-Type": "application/json", "X-CSRF-Token": csrfToken(), ...extra }; }
function hex(value: string | undefined, fallback: string) { return /^#[0-9a-f]{6}$/i.test(value ?? "") ? value! : fallback; }

/* ────────────────────────────────────────────────────
   Preview section renderer — looks like actual website
   ──────────────────────────────────────────────────── */
function PreviewSection({ section, template, brand, selected, onSelect }: { section: Section; template: TemplateKey; brand: Brand; selected: boolean; onSelect: () => void }) {
  const type = section.section_type;
  const content = section.content ?? {};
  const heading = content.heading || "";
  const body = content.body || "";
  const eyebrow = content.eyebrow || type.replaceAll("_", " ").toUpperCase();
  const items = content.items ?? [];
  const style = `template-${template}`;

  if (["hero", "banner"].includes(type)) {
    return (
      <section className={`public-hero ${style} wb-preview-block${selected ? " wb-selected" : ""}`} onClick={onSelect}>
        <div>
          <p className="public-eyebrow">{eyebrow}</p>
          <h1>{heading || "Care that feels considered."}</h1>
          {body && <p className="public-lede">{body}</p>}
          <span className={`button button-primary ${buttonClass(brand)}`}>{content.button_label || "Book an appointment"} <span>→</span></span>
        </div>
        {template === "calm_clinic" && <div className="public-hero-art" aria-hidden="true"><div className="public-hero-sun" /><div className="public-hero-card"><span>YOUR HEALTH, IN GOOD HANDS</span><strong>Make space for feeling well.</strong></div></div>}
      </section>
    );
  }

  if (["services", "service"].includes(type) || type === "pricing") {
    return (
      <section className={`public-section ${style} wb-preview-block${selected ? " wb-selected" : ""}`} onClick={onSelect}>
        <div className="public-section-heading"><p className="public-eyebrow">{eyebrow}</p><h2>{heading || "Our services"}</h2>{body && <p>{body}</p>}</div>
        <div className="public-record-grid">
          {(items.length > 0 ? items : [{ title: "Service 1" }, { title: "Service 2" }, { title: "Service 3" }]).map((item, i) => (
            <article className={`public-record ${style}-record`} key={i}><span className="public-record-number">{String(i + 1).padStart(2, "0")}</span><h3>{String(item.title ?? item.name ?? "Service")}</h3><p>{String(item.description ?? item.body ?? "")}</p></article>
          ))}
        </div>
      </section>
    );
  }

  if (["doctor_profile", "doctors", "team"].includes(type)) {
    return (
      <section className={`public-section ${style} wb-preview-block${selected ? " wb-selected" : ""}`} onClick={onSelect}>
        <div className="public-section-heading"><p className="public-eyebrow">YOUR CARE TEAM</p><h2>{heading || "Meet your doctors"}</h2>{body && <p>{body}</p>}</div>
        <div className="public-record-grid public-doctors">
          {(items.length > 0 ? items : [{ name: "Dr. A" }, { name: "Dr. B" }]).map((item, i) => (
            <article className={`public-record ${style}-record`} key={i}><div className="public-avatar" aria-hidden="true">{String(item.name ?? "D").slice(0, 1)}</div><h3>{String(item.name ?? item.public_name ?? "Doctor")}</h3><p>{String(item.specialty ?? item.bio ?? "")}</p></article>
          ))}
        </div>
      </section>
    );
  }

  if (["hours", "location", "contact"].includes(type)) {
    return (
      <section className={`public-section public-details ${style} wb-preview-block${selected ? " wb-selected" : ""}`} onClick={onSelect}>
        <div className="public-section-heading"><p className="public-eyebrow">{eyebrow}</p><h2>{heading || "Plan your visit"}</h2>{body && <p>{body}</p>}</div>
        <div className="public-detail-columns">
          {type === "location" && <div><h3>Location</h3><p>{content.location || content.address || "Contact for details"}</p></div>}
          {type === "hours" && <div><h3>Hours</h3>{items.map((item, i) => <p key={i}><strong>{String(item.day ?? item.weekday ?? "")}</strong> {String(item.hours ?? item.opens_at ?? "")}</p>)}</div>}
          {type === "contact" && <div><h3>Contact</h3><p>{body || "Get in touch"}</p></div>}
        </div>
      </section>
    );
  }

  if (type === "testimonials" || type === "statistics") {
    return (
      <section className={`public-section public-record-section public-${type} ${style} wb-preview-block${selected ? " wb-selected" : ""}`} onClick={onSelect}>
        <div className="public-section-heading"><p className="public-eyebrow">{eyebrow}</p><h2>{heading || "What patients say"}</h2>{body && <p>{body}</p>}</div>
        <div className="public-record-grid">
          {(items.length > 0 ? items : [{ quote: "Excellent care", name: "Patient" }]).map((item, i) => (
            <article className={`public-record ${style}-record`} key={i}><span className="public-record-number">{String(i + 1).padStart(2, "0")}</span><h3>{String(item.quote ?? item.title ?? item.value ?? "Testimonial")}</h3><p>{String(item.body ?? item.detail ?? item.name ?? "")}</p></article>
          ))}
        </div>
      </section>
    );
  }

  if (type === "results") {
    return (
      <section className={`public-section public-record-section public-results ${style} wb-preview-block${selected ? " wb-selected" : ""}`} onClick={onSelect}>
        <div className="public-section-heading"><p className="public-eyebrow">RESULTS</p><h2>{heading || "Real results"}</h2>{body && <p>{body}</p>}</div>
        <p className="public-results-empty">Before &amp; after photos appear here when approved.</p>
      </section>
    );
  }

  if (type === "appointment_cta" || type === "lead_form") {
    return (
      <section className={`public-section public-copy ${style} wb-preview-block${selected ? " wb-selected" : ""}`} onClick={onSelect}>
        <p className="public-eyebrow">{eyebrow}</p>
        <h2>{heading || (type === "lead_form" ? "Get in touch" : "Ready when you are")}</h2>
        {body && <p>{body}</p>}
        <span className={`button button-primary ${buttonClass(brand)}`}>{content.button_label || (type === "lead_form" ? "Send enquiry" : "Book an appointment")} <span>→</span></span>
      </section>
    );
  }

  return (
    <section className={`public-section public-copy ${style} wb-preview-block${selected ? " wb-selected" : ""}`} onClick={onSelect}>
      <p className="public-eyebrow">{eyebrow}</p>
      {heading && <h2>{heading}</h2>}
      {body && <p>{body}</p>}
      {content.button_label && <span className={`button button-primary ${buttonClass(brand)}`}>{content.button_label} <span>→</span></span>}
    </section>
  );
}

/* ────────────────────────────────────────────────────
   Device preview — scales content to simulate device widths
   ──────────────────────────────────────────────────── */
function DevicePreview({ device, children }: { device: Device; children: (ref: React.RefObject<HTMLDivElement | null>) => React.ReactNode }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const targetWidth = DEVICE_WIDTH[device];

  useEffect(() => {
    if (!targetWidth || !containerRef.current) { setScale(1); return; }
    const observer = new ResizeObserver(([entry]) => {
      const available = entry.contentRect.width - 48;
      setScale(available >= targetWidth ? 1 : available / targetWidth);
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [targetWidth]);

  const isScaled = targetWidth !== null;
  return (
    <div className="wb-center" ref={containerRef}>
      <div style={isScaled ? { width: `${targetWidth}px`, transform: `scale(${scale})`, transformOrigin: "top center", transition: "transform .3s ease, width .3s ease" } : undefined}>
        {children(contentRef)}
      </div>
    </div>
  );
}

/* ────────────────────────────────────────────────────
   Main editor component
   ──────────────────────────────────────────────────── */
export default function WebsiteEditorPage() {
  /* ── state ── */
  const [websites, setWebsites] = useState<Website[]>([]);
  const [website, setWebsite] = useState<Website | null>(null);
  const [page, setPage] = useState<Page | null>(null);
  const [pages, setPages] = useState<Page[]>([]);
  const pageIdRef = useRef<string | null>(null);
  const [sections, setSections] = useState<Section[]>([]);
  const [versions, setVersions] = useState<Version[]>([]);
  const domainsRef = useRef<Domain[]>([]);
  const [newWebsiteName, setNewWebsiteName] = useState("Synthetic Clinic Website");
  const [newTemplate, setNewTemplate] = useState<TemplateKey>("calm_clinic");
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [clinicSlug, setClinicSlug] = useState<string>("preview");
  const [validation, setValidation] = useState<Validation | null>(null);
  const [device, setDevice] = useState<Device>("desktop");
  const [rightTab, setRightTab] = useState<RightTab>("design");
  const [selectedSectionId, setSelectedSectionId] = useState<string | null>(null);
  const [showSectionLibrary, setShowSectionLibrary] = useState(false);
  const [dragIndex, setDragIndex] = useState<number | null>(null);

  useEffect(() => {
    if (website) document.body.classList.add("wb-editor-active");
    else document.body.classList.remove("wb-editor-active");
    return () => { document.body.classList.remove("wb-editor-active"); };
  }, [website]);

  const canEdit = permissions.includes("website.edit");
  const canPublish = permissions.includes("website.publish");
  const controlsDisabled = !canEdit || busy !== null;
  const selectedSection = sections.find((s) => s.id === selectedSectionId) ?? null;
  const brand = useMemo<Brand>(() => website?.brand ?? {}, [website]);
  const template = useMemo<TemplateKey>(() => templateKey(website?.template_key), [website]);

  /* ── API callbacks ── */
  const validateDraft = useCallback(async (selected: Website) => {
    try { setValidation(await request<Validation>(`/api/v1/websites/${selected.id}/validation`)); }
    catch (reason) { setValidation({ valid: false, code: "VALIDATION_UNAVAILABLE", message: reason instanceof Error ? reason.message : "Draft validation is unavailable." }); }
  }, []);

  const loadWebsite = useCallback(async (selected: Website) => {
    setBusy("load"); setWebsite(selected);
    try {
      const [pageRows, versionRows] = await Promise.all([request<Page[]>(`/api/v1/websites/${selected.id}/pages`), request<Version[]>(`/api/v1/websites/${selected.id}/versions`)]);
      setVersions(versionRows ?? []);
      const allPages = Array.isArray(pageRows) ? pageRows : [];
      allPages.sort((a, b) => a.slug === "home" ? -1 : b.slug === "home" ? 1 : a.title.localeCompare(b.title));
      setPages(allPages);
      const firstPage = allPages.find((p) => p.id === pageIdRef.current) ?? allPages[0] ?? null;
      pageIdRef.current = firstPage?.id ?? null;
      setPage(firstPage);
      setSections(firstPage ? (await request<Section[]>(`/api/v1/websites/${selected.id}/pages/${firstPage.id}/sections`)) ?? [] : []);
      setSelectedSectionId(null);
      void validateDraft(selected);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The website could not be loaded."); }
    finally { setBusy(null); setLoading(false); }
  }, [validateDraft]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [session, rows, domainRows] = await Promise.all([request<Session>("/api/v1/auth/me"), request<Website[]>("/api/v1/websites"), request<Domain[]>("/api/v1/websites/domains")]);
      setPermissions(session.permissions ?? []); if (session.clinic_slug) setClinicSlug(session.clinic_slug); setWebsites(rows ?? []); domainsRef.current = domainRows ?? [];
      if ((rows ?? [])[0]) await loadWebsite((rows ?? [])[0]); else setLoading(false);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The website workspace could not be loaded."); setLoading(false); }
  }, [loadWebsite]);

  useEffect(() => { void load(); }, [load]);

  async function createWebsite(event: FormEvent) {
    event.preventDefault(); setBusy("create-website");
    try {
      const created = await request<Website>("/api/v1/websites", { method: "POST", headers: writeHeaders(), body: JSON.stringify({ name: newWebsiteName, template_key: newTemplate, brand: {} }) });
      setWebsites((current) => [created, ...current]); await loadWebsite(created);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The website could not be created."); }
    finally { setBusy(null); }
  }

  async function saveSection(section: Section, next?: Partial<Section>) {
    if (!website || !page || !canEdit) return;
    const candidate = { ...section, ...next }; setBusy(section.id);
    try {
      const updated = await request<Section>(`/api/v1/websites/${website.id}/pages/${page.id}/sections/${section.id}`, { method: "PATCH", headers: writeHeaders(), body: JSON.stringify({ section_type: candidate.section_type, layout_key: candidate.layout_key, position: candidate.position, content: candidate.content, is_visible: candidate.is_visible, expected_version: section.version }) });
      setSections((current) => current.map((s) => s.id === section.id ? updated : s));
      setNotice("Draft saved."); void validateDraft(website);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The section could not be saved."); }
    finally { setBusy(null); }
  }

  async function addSectionFromLibrary(sectionType: string, layoutKey: string) {
    if (!website || !page || !canEdit) return; setBusy("add-section"); setShowSectionLibrary(false);
    try {
      const created = await request<Section>(`/api/v1/websites/${website.id}/pages/${page.id}/sections`, { method: "POST", headers: writeHeaders(), body: JSON.stringify({ section_type: sectionType, layout_key: layoutKey, position: sections.length, content: { ...defaultContent, heading: sectionType.replaceAll("_", " ").replace(/\b\w/g, (l) => l.toUpperCase()) }, is_visible: true }) });
      setSections((current) => [...current, created]); setSelectedSectionId(created.id); setRightTab("content"); void validateDraft(website);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The section could not be added."); }
    finally { setBusy(null); }
  }

  async function removeSection(section: Section) {
    if (!website || !page || !canEdit || !window.confirm("Remove this section from the draft?")) return; setBusy(section.id);
    try {
      await request(`/api/v1/websites/${website.id}/pages/${page.id}/sections/${section.id}`, { method: "DELETE", headers: writeHeaders(), body: JSON.stringify({ expected_version: section.version }) });
      setSections((current) => current.filter((s) => s.id !== section.id).map((s, i) => ({ ...s, position: i })));
      if (selectedSectionId === section.id) setSelectedSectionId(null); void validateDraft(website);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The section could not be removed."); }
    finally { setBusy(null); }
  }

  async function duplicateSection(section: Section) {
    if (!website || !page || !canEdit) return; setBusy(section.id);
    try {
      const created = await request<Section>(`/api/v1/websites/${website.id}/pages/${page.id}/sections`, { method: "POST", headers: writeHeaders(), body: JSON.stringify({ section_type: section.section_type, layout_key: section.layout_key, position: sections.length, content: section.content, is_visible: section.is_visible }) });
      setSections((current) => [...current, created]); void validateDraft(website);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The section could not be duplicated."); }
    finally { setBusy(null); }
  }

  async function reorderSections(next: Section[]) {
    if (!website || !page || !canEdit) return;
    const previous = sections;
    setSections(next.map((s, position) => ({ ...s, position }))); setBusy("reorder");
    try {
      await request(`/api/v1/website-library/websites/${website.id}/pages/${page.id}/reorder-sections`, { method: "POST", headers: writeHeaders(), body: JSON.stringify({ section_ids: next.map((s) => s.id) }) });
      setSections((await request<Section[]>(`/api/v1/websites/${website.id}/pages/${page.id}/sections`)) ?? []); void validateDraft(website);
    } catch (reason) { setSections(previous); setError(reason instanceof Error ? reason.message : "The sections could not be reordered."); }
    finally { setBusy(null); }
  }

  async function moveSection(index: number, direction: -1 | 1) {
    const other = index + direction;
    if (other < 0 || other >= sections.length) return;
    const next = [...sections]; [next[index], next[other]] = [next[other], next[index]];
    await reorderSections(next);
  }

  function dropSection(target: number) {
    if (dragIndex === null || dragIndex === target) { setDragIndex(null); return; }
    const next = [...sections]; const [moved] = next.splice(dragIndex, 1); next.splice(target, 0, moved);
    setDragIndex(null); void reorderSections(next);
  }

  async function selectPage(id: string) {
    const chosen = pages.find((p) => p.id === id);
    if (!website || !chosen) return;
    setBusy("page"); pageIdRef.current = chosen.id; setPage(chosen); setSelectedSectionId(null);
    try { setSections((await request<Section[]>(`/api/v1/websites/${website.id}/pages/${chosen.id}/sections`)) ?? []); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The page could not be loaded."); }
    finally { setBusy(null); }
  }

  async function createPageAction() {
    if (!website || !canEdit) return;
    const title = window.prompt("Page title")?.trim(); if (!title) return;
    const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "page";
    setBusy("page");
    try {
      const created = await request<Page>(`/api/v1/websites/${website.id}/pages`, { method: "POST", headers: writeHeaders(), body: JSON.stringify({ slug, title }) });
      pageIdRef.current = created.id; await load(); setNotice(`Page "${title}" created.`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The page could not be created."); setBusy(null); }
  }

  async function renamePageAction() {
    if (!website || !page || !canEdit) return;
    const title = window.prompt("New page title", page.title)?.trim(); if (!title || title === page.title) return;
    setBusy("page");
    try { await request(`/api/v1/websites/${website.id}/pages/${page.id}`, { method: "PATCH", headers: writeHeaders(), body: JSON.stringify({ expected_version: page.version, title }) }); await load(); setNotice("Page renamed."); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The page could not be renamed."); setBusy(null); }
  }

  async function deletePageAction() {
    if (!website || !page || !canEdit || !window.confirm(`Delete "${page.title}" and its sections from the draft?`)) return;
    setBusy("page");
    try { await request(`/api/v1/websites/${website.id}/pages/${page.id}`, { method: "DELETE", headers: writeHeaders(), body: JSON.stringify({ expected_version: page.version }) }); pageIdRef.current = null; await load(); setNotice("Page deleted."); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The page could not be deleted."); setBusy(null); }
  }

  async function toggleSectionVisibility(section: Section) {
    await saveSection(section, { is_visible: !section.is_visible });
  }

  async function updateBrand(patch: Partial<Brand>) {
    if (!website || !canEdit) return; setBusy("brand");
    try {
      const nextBrand = { ...(website.brand ?? {}), ...patch };
      const updated = await request<Website>(`/api/v1/websites/${website.id}`, { method: "PATCH", headers: writeHeaders(), body: JSON.stringify({ brand: nextBrand, expected_version: website.version }) });
      setWebsite(updated); setWebsites((current) => current.map((w) => w.id === updated.id ? updated : w)); await validateDraft(updated);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Brand settings could not be saved."); }
    finally { setBusy(null); }
  }

  async function saveTheme(patch: Pick<Brand, "theme" | "header" | "footer" | "seo" | "tablet" | "mobile">) {
    if (!website || !canEdit) return;
    const cleaned = Object.fromEntries(Object.entries(patch).filter(([, v]) => v !== undefined));
    const updated = await request<Website>(`/api/v1/websites/${website.id}`, { method: "PATCH", headers: writeHeaders(), body: JSON.stringify({ brand: { ...(website.brand ?? {}), ...cleaned }, expected_version: website.version }) });
    setWebsite(updated); setWebsites((current) => current.map((w) => w.id === updated.id ? updated : w)); void validateDraft(updated);
  }

  async function applyPreset(preset: ThemePreset) {
    if (!website || !canEdit) return; setBusy(`preset-${preset.key}`);
    try { await updateBrand(preset.brand); setNotice(`"${preset.name}" theme applied.`); }
    finally { setBusy(null); }
  }

  async function uploadLogo(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; if (!file || !website || !canEdit) return; setBusy("logo");
    try {
      const uploaded = await request<{ id: string }>("/api/v1/websites/media/upload", { method: "POST", headers: writeHeaders({ "Content-Type": file.type, "X-Original-Filename": file.name, "X-Alt-Text": "Clinic logo" }), body: file });
      await updateBrand({ logo_media_id: uploaded.id });
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The logo could not be uploaded."); }
    finally { setBusy(null); }
  }

  async function publish() {
    if (!website || !canPublish || !validation?.valid) return; setBusy("publish");
    try {
      setWebsite(await request<Website>(`/api/v1/websites/${website.id}/publish`, { method: "POST", headers: writeHeaders(), body: JSON.stringify({ expected_version: website.version }) }));
      setNotice("Published! The live site now uses this version.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Publishing failed."); }
    finally { setBusy(null); }
  }

  async function rollback(version: Version) {
    if (!website || !canPublish || !window.confirm(`Roll back to version ${version.version_number}?`)) return; setBusy("rollback");
    try {
      const result = await request<{ website: Website }>(`/api/v1/websites/${website.id}/rollback`, { method: "POST", headers: writeHeaders(), body: JSON.stringify({ source_version_id: version.id, expected_version: website.version }) });
      await loadWebsite(result.website);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Rollback failed."); }
    finally { setBusy(null); }
  }

  const warning = validation && !validation.valid ? validation.message : null;
  const sortedSections = useMemo(() => [...sections].sort((a, b) => a.position - b.position), [sections]);
  const visibleSections = useMemo(() => sortedSections.filter((s) => s.is_visible), [sortedSections]);

  /* ────────────────────────────────────────────────────
     Render
     ──────────────────────────────────────────────────── */

  /* ── Create form (no website) ── */
  if (!loading && !website) {
    return (
      <main className="website-editor" aria-busy={loading}>
        <div className="dash-topline"><div><p className="eyebrow">Website</p><h1>Shape your <em>front door.</em></h1></div></div>
        {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" type="button" onClick={() => { setError(null); void load(); }}>Try again <span>→</span></button></div>}
        <form className="setup-card website-create" onSubmit={createWebsite}>
          <p className="eyebrow">Get started</p>
          <h2>Create a clinic website</h2>
          <p className="setup-card-copy">Choose a template. Your first changes remain in draft until you publish them.</p>
          <label htmlFor="website-name">Website name</label>
          <input id="website-name" value={newWebsiteName} onChange={(e) => setNewWebsiteName(e.target.value)} required />
          <label htmlFor="website-template">Template
            <select id="website-template" value={newTemplate} onChange={(e) => setNewTemplate(templateKey(e.target.value))}>
              {templates.map((t) => <option value={t.key} key={t.key}>{t.label} · {t.description}</option>)}
            </select>
          </label>
          <button className="button button-primary" type="submit" disabled={!canEdit || busy !== null}>Create draft <span>→</span></button>
        </form>
      </main>
    );
  }

  if (loading || !website) {
    return <main className="website-editor" aria-busy><div className="dash-topline"><div><p className="eyebrow">Website</p><h1>Loading<em>…</em></h1></div></div></main>;
  }

  /* ── Three-panel editor ── */
  return (
    <main className="wb-editor" aria-busy={busy !== null}>
      {/* ═══ TOP BAR ═══ */}
      <header className="wb-topbar">
        <div className="wb-topbar-left">
          <button className="wb-icon-btn" onClick={() => { setWebsite(null); void load(); }} title="Exit editor">←</button>
          <h1 className="wb-topbar-title">{website.name}</h1>
          <div className="wb-topbar-context">
            <select className="wb-website-select" value={website.id} onChange={(e) => { const next = websites.find((w) => w.id === e.target.value); if (next) void loadWebsite(next); }}>
              {websites.map((w) => <option value={w.id} key={w.id}>{w.name}</option>)}
            </select>
            <span className="wb-status-badge" data-status={website.status}>{website.status === "published" ? "Published" : "Draft"}</span>
          </div>
        </div>
        <div className="wb-topbar-center">
          <div className="wb-device-bar">
            {(["desktop", "tablet", "mobile"] as const).map((d) => (
              <button key={d} className={`wb-device-btn${device === d ? " is-active" : ""}`} onClick={() => setDevice(d)} aria-pressed={device === d} title={d}>
                {d === "desktop" ? "🖥" : d === "tablet" ? "⊞" : "▮"}
              </button>
            ))}
          </div>
        </div>
        <div className="wb-topbar-right">
          <span className="wb-topbar-hint">{warning ? `⚠ ${warning}` : `v${website.version} · ${templateLabel(website.template_key)}`}</span>
          <button className="wb-btn wb-btn-secondary" onClick={async () => { if (!website) return; setBusy("preview"); try { const res = await request<{ preview_token: string; clinic_slug: string }>(`/api/v1/websites/${website.id}/preview-token`, { method: "POST", headers: writeHeaders() }); window.open(`/${encodeURIComponent(res.clinic_slug)}?preview_token=${encodeURIComponent(res.preview_token)}`, "_blank"); } catch { setError("Preview could not be opened — check that the API is reachable."); } finally { setBusy(null); } }} disabled={!website || busy !== null}>Preview</button>
          <button className="wb-btn wb-btn-secondary" onClick={() => void load()} disabled={busy !== null}>Refresh</button>
          <button className="wb-btn wb-btn-primary" style={{ fontWeight: 600 }} onClick={() => void publish()} disabled={!canPublish || !validation?.valid || busy !== null} title={!canPublish ? "Ask an owner to publish" : warning ?? "Publish this draft"}>
            {busy === "publish" ? "Publishing…" : "Publish"} <span>↑</span>
          </button>
        </div>
      </header>

      {/* ═══ ALERTS ═══ */}
      {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" onClick={() => { setError(null); void load(); }}>Try again <span>→</span></button></div>}
      {notice && <div className="website-notice" role="status">{notice}<button className="ghost-button" onClick={() => setNotice(null)}>Dismiss</button></div>}

      {/* ═══ THREE-PANEL BODY ═══ */}
      <div className="wb-body">
        {/* ─── LEFT SIDEBAR ─── */}
        <aside className="wb-left">
          <div className="wb-left-section">
            <div className="wb-left-header">
              <h3>Pages</h3>
              <button className="wb-add-btn" onClick={() => void createPageAction()} disabled={controlsDisabled} title="Add page">+</button>
            </div>
            <div className="wb-page-list">
              {pages.map((p) => (
                <button key={p.id} className={`wb-page-item${p.id === page?.id ? " is-active" : ""}`} onClick={() => void selectPage(p.id)} disabled={busy !== null}>
                  <span className="wb-page-icon">{p.slug === "home" ? "⌂" : "❏"}</span>
                  <span className="wb-page-label" title={p.title}>{p.title}</span>
                  <span className="wb-page-slug">/{p.slug}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="wb-left-section">
            <div className="wb-left-header">
              <h3>Sections{page ? ` · ${page.title}` : ""}</h3>
              <button className="wb-add-btn" onClick={() => setShowSectionLibrary(true)} disabled={controlsDisabled || !page} title="Add section">+</button>
            </div>
            <div className="wb-section-tree">
              {sortedSections.map((section, index) => (
                <div
                  key={section.id}
                  className={`wb-tree-item${section.id === selectedSectionId ? " is-active" : ""}${!section.is_visible ? " is-hidden" : ""}${dragIndex === index ? " is-dragging" : ""}`}
                  draggable={canEdit && busy === null}
                  onDragStart={() => setDragIndex(index)}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={() => dropSection(index)}
                  onDragEnd={() => setDragIndex(null)}
                  onClick={() => { setSelectedSectionId(section.id); setRightTab("content"); }}
                >
                  <span className="wb-tree-grip" title="Drag to reorder">⠿</span>
                  <span className="wb-tree-label">{section.section_type.replaceAll("_", " ")}</span>
                  <span className="wb-tree-pos">#{index + 1}</span>
                  <div className="wb-tree-actions">
                    <button className="wb-tree-btn" onClick={(e) => { e.stopPropagation(); void moveSection(index, -1); }} disabled={index === 0 || controlsDisabled} title="Move up">↑</button>
                    <button className="wb-tree-btn" onClick={(e) => { e.stopPropagation(); void moveSection(index, 1); }} disabled={index === sortedSections.length - 1 || controlsDisabled} title="Move down">↓</button>
                    <button className="wb-tree-btn" onClick={(e) => { e.stopPropagation(); void toggleSectionVisibility(section); }} disabled={controlsDisabled} title={section.is_visible ? "Hide" : "Show"}>
                      {section.is_visible ? "◉" : "◯"}
                    </button>
                  </div>
                </div>
              ))}
              {page && sortedSections.length === 0 && <p className="wb-empty">No sections yet. Add one to start building.</p>}
            </div>
          </div>
        </aside>

        {/* ─── CENTER PREVIEW ─── */}
        <DevicePreview device={device}>
          {(previewRef) => (
            <div className="wb-preview-viewport" ref={previewRef}>
              <div className="wb-preview-chrome">
                <span /><span /><span />
                <small>{page?.title ?? "Home"} · {templateLabel(website.template_key)} · {device}</small>
              </div>
              <div className="public-site has-theme wb-preview-site" style={themeStyle(brand, device) as CSSProperties}>
                <SiteHeader brand={brand} clinicSlug={clinicSlug} />
                <div className="public-shell">
                  {visibleSections.map((section) => (
                    <PreviewSection
                      key={section.id}
                      section={section}
                      template={template}
                      brand={brand}
                      selected={section.id === selectedSectionId}
                      onSelect={() => { setSelectedSectionId(section.id); setRightTab("content"); }}
                    />
                  ))}
                  {visibleSections.length === 0 && (
                    <div className="wb-preview-empty">
                      <p>This page has no visible sections.</p>
                      <button className="wb-btn wb-btn-secondary" onClick={() => setShowSectionLibrary(true)} disabled={controlsDisabled}>Add a section</button>
                    </div>
                  )}
                </div>
                <SiteFooter brand={brand} title={website.name} clinicSlug={clinicSlug} />
              </div>
            </div>
          )}
        </DevicePreview>

        {/* ─── RIGHT SIDEBAR ─── */}
        <aside className="wb-right">
          <nav className="wb-right-tabs">
            {([
              { key: "design" as RightTab, label: "Design", icon: "◑" },
              { key: "content" as RightTab, label: selectedSection ? "Section" : "Content", icon: "✎" },
              { key: "page" as RightTab, label: "Page", icon: "❏" },
              { key: "seo" as RightTab, label: "SEO", icon: "⌕" },
              { key: "library" as RightTab, label: "Library", icon: "❖" },
              { key: "history" as RightTab, label: "History", icon: "↺" },
            ]).map((tab) => (
              <button key={tab.key} className={`wb-rtab${rightTab === tab.key ? " is-active" : ""}`} onClick={() => setRightTab(tab.key)}>
                <span aria-hidden="true">{tab.icon}</span> {tab.label}
              </button>
            ))}
          </nav>

          <div className="wb-right-body">
            {/* ── Design tab ── */}
            {rightTab === "design" && <>
              <section className="wb-panel">
                <h3>Theme presets</h3>
                <div className="preset-grid">
                  {themePresets.map((preset) => (
                    <button key={preset.key} type="button" className="preset-tile" disabled={controlsDisabled} onClick={() => void applyPreset(preset)}>
                      <span className="preset-swatch" aria-hidden="true">{preset.swatch.map((c, i) => <i key={i} style={{ background: c }} />)}</span>
                      <strong>{preset.name}</strong><small>{preset.blurb}</small>
                    </button>
                  ))}
                </div>
              </section>
              <section className="wb-panel">
                <h3>Brand colors</h3>
                <div className="wb-color-grid">
                  <label>Primary<input type="color" value={hex(brand.theme?.colors?.primary ?? brand.primary_color, "#274c42")} onChange={(e) => void updateBrand({ theme: { ...brand.theme, colors: { ...brand.theme?.colors, primary: e.target.value } } })} disabled={controlsDisabled} /></label>
                  <label>Accent<input type="color" value={hex(brand.theme?.colors?.accent ?? brand.accent_color, "#e77b5c")} onChange={(e) => void updateBrand({ theme: { ...brand.theme, colors: { ...brand.theme?.colors, accent: e.target.value } } })} disabled={controlsDisabled} /></label>
                  <label>Text<input type="color" value={hex(brand.theme?.colors?.text ?? brand.text_color, "#1c2928")} onChange={(e) => void updateBrand({ theme: { ...brand.theme, colors: { ...brand.theme?.colors, text: e.target.value } } })} disabled={controlsDisabled} /></label>
                  <label>Background<input type="color" value={hex(brand.theme?.colors?.background ?? brand.background_color, "#f5f4ee")} onChange={(e) => void updateBrand({ theme: { ...brand.theme, colors: { ...brand.theme?.colors, background: e.target.value } } })} disabled={controlsDisabled} /></label>
                </div>
              </section>
              <section className="wb-panel">
                <h3>Fonts &amp; logo</h3>
                <div className="wb-field-stack">
                  <label>Font pairing
                    <select value={brand.font_pairing ?? "dm-sans-fraunces"} onChange={(e) => void updateBrand({ font_pairing: e.target.value })} disabled={controlsDisabled}>
                      <option value="dm-sans-fraunces">DM Sans + Fraunces</option>
                      <option value="system-serif">System sans + serif</option>
                    </select>
                  </label>
                  <label>Logo
                    <input type="file" accept="image/jpeg,image/png,image/webp" onChange={uploadLogo} disabled={controlsDisabled} />
                    <small>{brand.logo_media_id ? "Logo uploaded" : "PNG, JPG, or WebP"}</small>
                  </label>
                </div>
              </section>
              <ThemePanel key={`theme-${website.id}`} brand={brand} disabled={controlsDisabled} onSave={saveTheme} />
            </>}

            {/* ── Content/Section tab ── */}
            {rightTab === "content" && selectedSection && (
              <section className="wb-panel">
                <div className="wb-panel-header">
                  <h3>{selectedSection.section_type.replaceAll("_", " ")}</h3>
                  <span className="wb-panel-meta">v{selectedSection.version}</span>
                </div>
                <div className="wb-field-stack">
                  <label>Layout
                    <select value={selectedSection.layout_key} onChange={(e) => setSections((current) => current.map((s) => s.id === selectedSection.id ? { ...s, layout_key: e.target.value } : s))} disabled={!canEdit}>
                      {(SECTION_LIBRARY.flatMap((c) => c.types).filter((t) => t.type === selectedSection.section_type).map((t) => (
                        <option key={t.layout} value={t.layout}>{t.label}</option>
                      )))}
                      {SECTION_LIBRARY.flatMap((c) => c.types).filter((t) => t.type === selectedSection.section_type).every((t) => t.layout !== selectedSection.layout_key) && (
                        <option value={selectedSection.layout_key}>{selectedSection.layout_key}</option>
                      )}
                    </select>
                  </label>
                  <label>Heading
                    <input value={selectedSection.content.heading} onChange={(e) => setSections((current) => current.map((s) => s.id === selectedSection.id ? { ...s, content: { ...s.content, heading: e.target.value } } : s))} disabled={!canEdit} />
                  </label>
                  <label>Body
                    <textarea rows={4} value={selectedSection.content.body} onChange={(e) => setSections((current) => current.map((s) => s.id === selectedSection.id ? { ...s, content: { ...s.content, body: e.target.value } } : s))} disabled={!canEdit} />
                  </label>
                  <label>Button label
                    <input value={selectedSection.content.button_label ?? ""} onChange={(e) => setSections((current) => current.map((s) => s.id === selectedSection.id ? { ...s, content: { ...s.content, button_label: e.target.value || null } } : s))} disabled={!canEdit} placeholder="e.g. Book an appointment" />
                  </label>
                  <label>Button link
                    <input value={selectedSection.content.button_href ?? ""} onChange={(e) => setSections((current) => current.map((s) => s.id === selectedSection.id ? { ...s, content: { ...s.content, button_href: e.target.value || null } } : s))} disabled={!canEdit} placeholder="/book or #contact" />
                  </label>
                  <label>Eyebrow text
                    <input value={selectedSection.content.eyebrow ?? ""} onChange={(e) => setSections((current) => current.map((s) => s.id === selectedSection.id ? { ...s, content: { ...s.content, eyebrow: e.target.value } } : s))} disabled={!canEdit} placeholder="Short label above heading" />
                  </label>
                  {["hours", "location", "contact"].includes(selectedSection.section_type) && <>
                    <label>Location
                      <input value={selectedSection.content.location ?? ""} onChange={(e) => setSections((current) => current.map((s) => s.id === selectedSection.id ? { ...s, content: { ...s.content, location: e.target.value } } : s))} disabled={!canEdit} />
                    </label>
                    <label>Address
                      <input value={selectedSection.content.address ?? ""} onChange={(e) => setSections((current) => current.map((s) => s.id === selectedSection.id ? { ...s, content: { ...s.content, address: e.target.value } } : s))} disabled={!canEdit} />
                    </label>
                  </>}
                </div>

                {/* items list editor for sections with repeatable items */}
                {["services", "pricing", "doctor_profile", "testimonials", "statistics", "hours", "faq", "results"].includes(selectedSection.section_type) && (
                  <div className="wb-items-editor">
                    <div className="wb-panel-header" style={{ marginTop: 16 }}>
                      <h3>Items</h3>
                      <button className="wb-add-btn" disabled={!canEdit} onClick={() => setSections((current) => current.map((s) => s.id === selectedSection.id ? { ...s, content: { ...s.content, items: [...(s.content.items ?? []), { title: "New item", description: "" }] } } : s))} title="Add item">+</button>
                    </div>
                    {(selectedSection.content.items ?? []).map((item, idx) => (
                      <div key={idx} className="wb-item-card">
                        <div className="wb-item-header">
                          <span className="wb-tree-pos">#{idx + 1}</span>
                          <button className="wb-tree-btn" disabled={!canEdit} onClick={() => setSections((current) => current.map((s) => s.id === selectedSection.id ? { ...s, content: { ...s.content, items: (s.content.items ?? []).filter((_, i) => i !== idx) } } : s))} title="Remove item">✕</button>
                        </div>
                        <div className="wb-field-stack">
                          <label>Title
                            <input value={String(item.title ?? item.name ?? item.quote ?? item.value ?? "")} onChange={(e) => setSections((current) => current.map((s) => { if (s.id !== selectedSection.id) return s; const items = [...(s.content.items ?? [])]; items[idx] = { ...items[idx], title: e.target.value }; return { ...s, content: { ...s.content, items } }; }))} disabled={!canEdit} />
                          </label>
                          <label>Description
                            <input value={String(item.description ?? item.body ?? item.detail ?? item.hours ?? "")} onChange={(e) => setSections((current) => current.map((s) => { if (s.id !== selectedSection.id) return s; const items = [...(s.content.items ?? [])]; items[idx] = { ...items[idx], description: e.target.value }; return { ...s, content: { ...s.content, items } }; }))} disabled={!canEdit} />
                          </label>
                        </div>
                      </div>
                    ))}
                    {(selectedSection.content.items ?? []).length === 0 && <p className="wb-empty">No items. Add one to populate this section.</p>}
                  </div>
                )}

                <div className="wb-section-actions">
                  <button className="wb-btn wb-btn-primary" onClick={() => void saveSection(selectedSection)} disabled={controlsDisabled}>Save section</button>
                  <button className="wb-btn wb-btn-secondary" onClick={() => void duplicateSection(selectedSection)} disabled={controlsDisabled}>Duplicate</button>
                  <button className="wb-btn wb-btn-danger" onClick={() => void removeSection(selectedSection)} disabled={controlsDisabled}>Remove</button>
                </div>
              </section>
            )}
            {rightTab === "content" && !selectedSection && (
              <div className="wb-panel wb-panel-empty">
                <p>Select a section from the tree or preview to edit its content.</p>
              </div>
            )}

            {/* ── Page tab ── */}
            {rightTab === "page" && page && (
              <>
                <section className="wb-panel">
                  <h3>Page settings</h3>
                  <div className="wb-field-stack">
                    <label>Page title<input value={page.title} readOnly /></label>
                    <label>URL slug<input value={`/${page.slug}`} readOnly /></label>
                    {page.seo_title !== undefined && <label>SEO title<input value={page.seo_title ?? ""} readOnly /></label>}
                    {page.seo_description !== undefined && <label>Meta description<input value={page.seo_description ?? ""} readOnly /></label>}
                  </div>
                  <div className="wb-section-actions">
                    <button className="wb-btn wb-btn-secondary" onClick={() => void renamePageAction()} disabled={controlsDisabled}>Rename page</button>
                    <button className="wb-btn wb-btn-secondary" onClick={() => setRightTab("seo")} disabled={controlsDisabled}>Edit SEO</button>
                    <button className="wb-btn wb-btn-danger" onClick={() => void deletePageAction()} disabled={controlsDisabled || page.slug === "home"}>Delete page</button>
                  </div>
                </section>
                {domainsRef.current.length > 0 && (
                  <section className="wb-panel">
                    <h3>Custom domains</h3>
                    <div className="wb-version-list">
                      {domainsRef.current.map((d) => (
                        <div className="wb-version-row" key={d.hostname}>
                          <div><strong>{d.hostname}</strong><small>{d.observed_status}</small></div>
                        </div>
                      ))}
                    </div>
                  </section>
                )}
              </>
            )}

            {/* ── SEO tab ── */}
            {rightTab === "seo" && website && <SeoPanel key={`seo-${website.id}`} website={website} disabled={controlsDisabled} onSaveSeo={(seo) => saveTheme({ seo })} />}

            {/* ── Library tab ── */}
            {rightTab === "library" && website && <LibraryPanel key={`lib-${website.id}`} website={website} pageId={page?.id ?? null} sections={sections} disabled={controlsDisabled} onChanged={() => void load()} />}

            {/* ── History tab ── */}
            {rightTab === "history" && (
              <section className="wb-panel">
                <h3>Version history</h3>
                <p className="wb-panel-meta">{versions.length} versions</p>
                <div className="wb-version-list">
                  {versions.map((version) => (
                    <div className="wb-version-row" key={version.id}>
                      <div>
                        <strong>Version {version.version_number}</strong>
                        <small>{version.published_at ? "Published" : "Draft"} · {new Date(version.created_at).toLocaleDateString()}</small>
                      </div>
                      <button className="wb-btn wb-btn-secondary" onClick={() => void rollback(version)} disabled={!canPublish || busy !== null}>Roll back</button>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        </aside>
      </div>

      {/* ═══ SECTION LIBRARY MODAL ═══ */}
      {showSectionLibrary && (
        <div className="wb-modal-backdrop" onClick={() => setShowSectionLibrary(false)}>
          <div className="wb-modal wb-section-library-modal" onClick={(e) => e.stopPropagation()}>
            <div className="wb-modal-header">
              <h2>Add a section</h2>
              <button className="wb-icon-btn wb-modal-close" onClick={() => setShowSectionLibrary(false)}>✕</button>
            </div>
            <div className="wb-lib-grid">
              {SECTION_LIBRARY.map((category) => (
                <div key={category.label} className="wb-lib-category">
                  <h4><span>{category.icon}</span> {category.label}</h4>
                  <div className="wb-lib-items">
                    {category.types.map((item) => (
                      <button key={`${item.type}-${item.layout}`} className="wb-lib-item" onClick={() => void addSectionFromLibrary(item.type, item.layout)} disabled={controlsDisabled}>
                        <strong>{item.label}</strong>
                        <small>{item.description}</small>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

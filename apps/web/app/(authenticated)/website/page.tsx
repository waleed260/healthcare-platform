"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, CSSProperties, FormEvent } from "react";
import { useRouter } from "next/navigation";
import ThemePanel from "./theme-panel";
import LibraryPanel from "./library-panel";
import SeoPanel from "./seo-panel";
import { SiteHeader, SiteFooter } from "../../[clinicSlug]/site-chrome";
import { themeStyle, buttonClass } from "../../site-theme";
import type { SiteBrand } from "../../site-theme";
import { api, csrfToken, writeHeaders as sharedWriteHeaders } from "../_lib/client";

/* ────────────────────────────────────────────────────
   Types
   ──────────────────────────────────────────────────── */
type Brand = SiteBrand;
type Website = { id: string; name: string; template_key: string; status: string; version: number; brand?: Brand; draft_version_id?: string | null; live_version_id?: string | null };
type Page = { id: string; slug: string; title: string; version: number; seo_title?: string | null; seo_description?: string | null };
type Content = { heading: string; body: string; eyebrow?: string; button_label?: string | null; button_href?: string | null; items?: Array<Record<string, unknown>>; location?: string; address?: string; media_id?: string | null; gallery_ids?: string[]; custom_css?: string; design?: Record<string, unknown> };
type MediaAsset = { id: string; original_filename?: string; alt_text: string; mime_type: string; scan_status: string };
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
    { type: "video", layout: "default", label: "Video", description: "Embedded video player" },
    { type: "timeline", layout: "default", label: "Timeline", description: "Step-by-step process" },
    { type: "gallery", layout: "default", label: "Gallery", description: "Image gallery grid" },
    { type: "comparison", layout: "default", label: "Comparison", description: "Feature comparison table" },
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

type ThemeInstance = { id: string; name: string; status: string; brand_snapshot: Brand; version: number; created_at: string; updated_at?: string };
type RightTab = "design" | "content" | "page" | "seo" | "library" | "history" | "themes";

/* ────────────────────────────────────────────────────
   Helpers
   ──────────────────────────────────────────────────── */
async function request<T>(url: string, init?: RequestOptions): Promise<T> {
  return api<T>(url, init);
}
function writeHeaders(extra?: Record<string, string>) { return { "Content-Type": "application/json", "X-CSRF-Token": csrfToken(), ...extra }; }
function hex(value: string | undefined, fallback: string) { return /^#[0-9a-f]{6}$/i.test(value ?? "") ? value! : fallback; }

/* ────────────────────────────────────────────────────
   CodeMirror CSS editor (loaded dynamically from CDN)
   ──────────────────────────────────────────────────── */
declare global { interface Window { CodeMirror?: { fromTextArea: (el: HTMLTextAreaElement, opts: Record<string, unknown>) => { getValue: () => string; on: (ev: string, cb: () => void) => void; toTextArea: () => void }; } } }
const CM_BASE = "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18";
let cmLoadPromise: Promise<boolean> | null = null;
function loadCodeMirror(): Promise<boolean> {
  if (cmLoadPromise) return cmLoadPromise;
  cmLoadPromise = new Promise((resolve) => {
    if (window.CodeMirror) { resolve(true); return; }
    const script = document.createElement("script");
    script.src = `${CM_BASE}/codemirror.min.js`;
    script.onload = () => { const mode = document.createElement("script"); mode.src = `${CM_BASE}/mode/css/css.min.js`; mode.onload = () => resolve(true); mode.onerror = () => resolve(false); document.head.appendChild(mode); };
    script.onerror = () => resolve(false);
    document.head.appendChild(script);
    const link = document.createElement("link"); link.rel = "stylesheet"; link.href = `${CM_BASE}/codemirror.min.css`; document.head.appendChild(link);
  });
  return cmLoadPromise;
}
function CssEditor({ value, disabled, onChange }: { value: string; disabled: boolean; onChange: (v: string) => void }) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const cmRef = useRef<ReturnType<NonNullable<Window["CodeMirror"]>["fromTextArea"]> | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    loadCodeMirror().then((ok) => { if (!cancelled && ok) setLoaded(true); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!loaded || !textareaRef.current || cmRef.current || disabled) return;
    const cm = window.CodeMirror!.fromTextArea(textareaRef.current, { mode: "css", lineNumbers: true, theme: "default", indentUnit: 2, tabSize: 2, lineWrapping: true });
    cm.on("change", () => onChangeRef.current(cm.getValue()));
    cmRef.current = cm;
    return () => { cmRef.current?.toTextArea(); cmRef.current = null; };
  }, [loaded, disabled]);

  return <div className="wb-field-stack" style={{ marginTop: 16 }}><label style={{ display: "block", marginBottom: 4, fontSize: "0.78rem", fontWeight: 500 }}>Custom CSS</label><textarea ref={textareaRef} className="wb-css-editor" rows={6} placeholder={"/* Scoped to this section */\n.public-hero {\n  background: linear-gradient(...);\n}"} value={value} disabled={disabled} style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace", fontSize: "0.78rem", width: "100%", border: "1px solid var(--wb-border, #e5e5e3)", borderRadius: 4, padding: "8px 10px" }} onChange={(e) => onChange(e.target.value)} /></div>;
}

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
   Media picker — selects clean media for section images
   ──────────────────────────────────────────────────── */
function MediaPicker({ websiteId, sectionId, mediaId, galleryIds, isGallery, disabled, onSelect, onGalleryChange }: {
  websiteId: string | null; sectionId: string; mediaId: string | null; galleryIds: string[]; isGallery: boolean; disabled: boolean;
  onSelect: (id: string | null) => void; onGalleryChange: (ids: string[]) => void;
}) {
  const [items, setItems] = useState<MediaAsset[]>([]);
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    if (!websiteId) return;
    try {
      const rows = await api<MediaAsset[]>("/api/v1/websites/media?limit=100");
      setItems((rows ?? []).filter((m) => m.scan_status === "clean" && m.mime_type.startsWith("image/")));
    } catch { /* graceful */ }
    setLoaded(true);
  }, [websiteId]);

  useEffect(() => { if (open && !loaded) void load(); }, [open, loaded, load]);

  const selectedName = mediaId ? items.find((m) => m.id === mediaId)?.alt_text || items.find((m) => m.id === mediaId)?.original_filename || "Selected" : null;

  if (isGallery) {
    return (
      <div>
        <div className="wb-panel-header"><h3>Gallery images</h3><button className="wb-add-btn" disabled={disabled} onClick={() => setOpen((v) => !v)} title="Pick images">+</button></div>
        {galleryIds.length > 0 && <div className="wb-version-list">{galleryIds.map((gid, idx) => {
          const asset = items.find((m) => m.id === gid);
          return <div className="wb-version-row" key={gid}><div><strong>{asset?.alt_text || asset?.original_filename || `Image ${idx + 1}`}</strong><small>{asset?.mime_type ?? ""}</small></div><button className="wb-tree-btn" disabled={disabled} onClick={() => onGalleryChange(galleryIds.filter((_, i) => i !== idx))} title="Remove">✕</button></div>;
        })}</div>}
        {galleryIds.length === 0 && <p className="wb-empty">No gallery images selected.</p>}
        {open && <div className="wb-version-list" style={{ marginTop: 8, maxHeight: 200, overflowY: "auto", border: "1px solid var(--border-subtle, #e5e5e3)", borderRadius: 6, padding: 4 }}>
          {items.filter((m) => !galleryIds.includes(m.id)).map((m) => <button key={m.id} className="wb-version-row" style={{ cursor: "pointer", width: "100%", textAlign: "left", background: "none", border: "none" }} onClick={() => { onGalleryChange([...galleryIds, m.id]); }}><div><strong>{m.alt_text || m.original_filename}</strong><small>{m.mime_type}</small></div></button>)}
          {items.filter((m) => !galleryIds.includes(m.id)).length === 0 && <p className="wb-empty">{loaded ? "No more images available." : "Loading…"}</p>}
        </div>}
      </div>
    );
  }

  return (
    <div>
      <label>Section image
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button className="wb-btn wb-btn-secondary" style={{ flex: 1 }} disabled={disabled} onClick={() => setOpen((v) => !v)} type="button">{selectedName ?? "Choose image…"}</button>
          {mediaId && <button className="wb-tree-btn" disabled={disabled} onClick={() => onSelect(null)} title="Remove image">✕</button>}
        </div>
      </label>
      {open && <div className="wb-version-list" style={{ marginTop: 4, maxHeight: 200, overflowY: "auto", border: "1px solid var(--border-subtle, #e5e5e3)", borderRadius: 6, padding: 4 }}>
        {items.map((m) => <button key={m.id} className="wb-version-row" style={{ cursor: "pointer", width: "100%", textAlign: "left", background: mediaId === m.id ? "var(--accent-bg, #edf6f3)" : "none", border: "none" }} onClick={() => { onSelect(m.id); setOpen(false); }}><div><strong>{m.alt_text || m.original_filename}</strong><small>{m.mime_type}</small></div></button>)}
        {items.length === 0 && <p className="wb-empty">{loaded ? "No clean images in media library." : "Loading…"}</p>}
      </div>}
    </div>
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
  const router = useRouter();
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
  const [themeInstances, setThemeInstances] = useState<ThemeInstance[]>([]);
  const [newThemeName, setNewThemeName] = useState("");

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
  const validateDraft = useCallback(async (selected: Website, currentPages?: Page[]) => {
    try {
      const serverResult = await request<Validation>(`/api/v1/websites/${selected.id}/validation`);
      if (serverResult && !serverResult.valid) { setValidation(serverResult); return; }
      const knownPages = currentPages?.length ? currentPages : (await request<Page[]>(`/api/v1/websites/${selected.id}/pages`)) ?? [];
      const hasLegal = knownPages.some((p) => /privacy|terms|legal|policy/i.test(p.slug));
      if (!hasLegal) { setValidation({ valid: false, code: "MISSING_LEGAL", message: "Add a privacy policy or terms page before publishing." }); return; }
      const colors = selected.brand?.theme?.colors;
      if (colors?.primary && colors?.background) {
        const lum = (hex: string) => { const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; };
        const l1 = lum(colors.primary); const l2 = lum(colors.background);
        const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
        if (ratio < 4.5) { setValidation({ valid: false, code: "LOW_CONTRAST", message: `Primary/background contrast ratio is ${ratio.toFixed(1)}:1 — WCAG AA requires at least 4.5:1.` }); return; }
      }
      setValidation(serverResult);
    } catch (reason) { setValidation({ valid: false, code: "VALIDATION_UNAVAILABLE", message: reason instanceof Error ? reason.message : "Draft validation is unavailable." }); }
  }, []);

  const loadWebsite = useCallback(async (selected: Website) => {
    setBusy("load"); setWebsite(selected);
    try {
      const [detail, pageRows, versionRows, themeRows] = await Promise.all([request<Website>(`/api/v1/websites/${selected.id}`).catch(() => null), request<Page[]>(`/api/v1/websites/${selected.id}/pages`), request<Version[]>(`/api/v1/websites/${selected.id}/versions`), request<ThemeInstance[]>(`/api/v1/websites/${selected.id}/themes`).catch(() => [] as ThemeInstance[])]);
      const ws = detail ?? selected;
      setWebsite(ws); setWebsites((current) => current.map((w) => w.id === ws.id ? ws : w));
      setVersions(versionRows ?? []); setThemeInstances(themeRows ?? []);
      const allPages = Array.isArray(pageRows) ? pageRows : [];
      allPages.sort((a, b) => a.slug === "home" ? -1 : b.slug === "home" ? 1 : a.title.localeCompare(b.title));
      setPages(allPages);
      const firstPage = allPages.find((p) => p.id === pageIdRef.current) ?? allPages[0] ?? null;
      pageIdRef.current = firstPage?.id ?? null;
      setPage(firstPage);
      setSections(firstPage ? (await request<Section[]>(`/api/v1/websites/${ws.id}/pages/${firstPage.id}/sections`)) ?? [] : []);
      setSelectedSectionId(null);
      void validateDraft(ws, allPages);
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
          <button className="wb-icon-btn" onClick={() => router.back()} title="Exit editor">←</button>
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
                    <div key={section.id} className={`wb-section-wrap section-${section.section_type}`}>
                      {section.content.custom_css && <style>{section.content.custom_css}</style>}
                      <PreviewSection
                        section={section}
                        template={template}
                        brand={brand}
                        selected={section.id === selectedSectionId}
                        onSelect={() => { setSelectedSectionId(section.id); setRightTab("content"); }}
                      />
                    </div>
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
              { key: "themes" as RightTab, label: "Themes", icon: "◈" },
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
                  {["services", "pricing", "doctor_profile", "testimonials", "statistics"].includes(selectedSection.section_type) && (() => {
                    const dataMode = (selectedSection.content as Record<string, unknown>).data_mode as string | undefined;
                    const isManual = dataMode === "manual";
                    return <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0" }}>
                      <span style={{ fontSize: "0.6rem", fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase" as const, padding: "2px 7px", borderRadius: 3, background: isManual ? "#fef8ed" : "#eaf7f0", color: isManual ? "#b5740a" : "#1a7f4b" }}>{isManual ? "MANUAL" : "DYNAMIC"}</span>
                      <select value={dataMode ?? "dynamic"} onChange={(e) => setSections((current) => current.map((s) => s.id === selectedSection.id ? { ...s, content: { ...s.content, data_mode: e.target.value } } : s))} disabled={!canEdit} style={{ flex: 1 }}>
                        <option value="dynamic">Dynamic — from CRM records</option>
                        <option value="manual">Manual — inline items only</option>
                      </select>
                    </div>;
                  })()}
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

                {/* media picker for sections that support images */}
                {["hero", "results", "doctor_profile", "about"].includes(selectedSection.section_type) && (() => {
                  const isGallery = selectedSection.section_type === "results";
                  return (
                    <div className="wb-field-stack" style={{ marginTop: 12 }}>
                      <MediaPicker
                        websiteId={website?.id ?? null}
                        sectionId={selectedSection.id}
                        mediaId={selectedSection.content.media_id ?? null}
                        galleryIds={selectedSection.content.gallery_ids ?? []}
                        isGallery={isGallery}
                        disabled={!canEdit}
                        onSelect={(id) => setSections((cur) => cur.map((s) => s.id === selectedSection.id ? { ...s, content: { ...s.content, media_id: id } } : s))}
                        onGalleryChange={(ids) => setSections((cur) => cur.map((s) => s.id === selectedSection.id ? { ...s, content: { ...s.content, gallery_ids: ids } } : s))}
                      />
                    </div>
                  );
                })()}

                {/* items list editor for sections with repeatable items */}
                {["services", "pricing", "doctor_profile", "testimonials", "statistics"].includes(selectedSection.section_type) && (selectedSection.content as Record<string, unknown>).data_mode !== "manual" && (
                  <div style={{ margin: "12px 0", padding: "8px 12px", background: "var(--done-bg, #eaf7f0)", borderRadius: 6, fontSize: "0.78rem", color: "var(--done, #1a7f4b)" }}>
                    <strong>Dynamic mode</strong> — content pulled from CRM records (services, doctors, testimonials). Switch to Manual to edit items inline.
                  </div>
                )}
                {(["hours", "faq", "results"].includes(selectedSection.section_type) || ((selectedSection.content as Record<string, unknown>).data_mode === "manual" && ["services", "pricing", "doctor_profile", "testimonials", "statistics"].includes(selectedSection.section_type))) && (
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

                <fieldset className="wb-design-fieldset" style={{ marginTop: 16, border: "1px solid var(--wb-border, #e5e5e3)", borderRadius: 6, padding: "12px 14px" }}>
                  <legend style={{ fontSize: "0.7rem", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--wb-muted, #6b7280)", padding: "0 6px" }}>Section Design</legend>
                  {(() => { const design = (selectedSection.content.design ?? {}) as Record<string, unknown>; const setDesign = (key: string, value: unknown) => setSections((current) => current.map((s) => s.id === selectedSection.id ? { ...s, content: { ...s.content, design: { ...(s.content.design as Record<string, unknown> ?? {}), [key]: value } } } : s)); return <>
                    <div className="wb-design-row" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
                      <label className="wb-design-label">Background color
                        <input type="color" value={String(design.background_color || "#ffffff")} onChange={(e) => setDesign("background_color", e.target.value)} disabled={!canEdit} style={{ width: "100%", height: 28, cursor: "pointer" }} />
                      </label>
                      <label className="wb-design-label">Overlay color
                        <input type="color" value={String(design.overlay_color || "#000000")} onChange={(e) => setDesign("overlay_color", e.target.value)} disabled={!canEdit} style={{ width: "100%", height: 28, cursor: "pointer" }} />
                      </label>
                    </div>
                    <label className="wb-design-label" style={{ marginBottom: 8, display: "block" }}>Background image URL
                      <input type="url" value={String(design.background_image || "")} onChange={(e) => setDesign("background_image", e.target.value || null)} disabled={!canEdit} placeholder="https://..." style={{ width: "100%" }} />
                    </label>
                    <label className="wb-design-label" style={{ marginBottom: 8, display: "block" }}>Overlay opacity: {Number(design.overlay_opacity ?? 0)}%
                      <input type="range" min={0} max={100} value={Number(design.overlay_opacity ?? 0)} onChange={(e) => setDesign("overlay_opacity", Number(e.target.value))} disabled={!canEdit} style={{ width: "100%" }} />
                    </label>
                    <div className="wb-design-row" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
                      <label className="wb-design-label">Padding top (px)
                        <input type="number" min={0} max={200} value={Number(design.padding_top ?? "")} onChange={(e) => setDesign("padding_top", e.target.value ? Number(e.target.value) : null)} disabled={!canEdit} placeholder="auto" />
                      </label>
                      <label className="wb-design-label">Padding bottom (px)
                        <input type="number" min={0} max={200} value={Number(design.padding_bottom ?? "")} onChange={(e) => setDesign("padding_bottom", e.target.value ? Number(e.target.value) : null)} disabled={!canEdit} placeholder="auto" />
                      </label>
                    </div>
                    <label className="wb-design-label" style={{ marginBottom: 8, display: "block" }}>Content width
                      <select value={String(design.content_width || "full")} onChange={(e) => setDesign("content_width", e.target.value === "full" ? null : e.target.value)} disabled={!canEdit} style={{ width: "100%" }}>
                        <option value="full">Full width</option>
                        <option value="contained">Contained (960px)</option>
                        <option value="narrow">Narrow (720px)</option>
                      </select>
                    </label>
                    <div style={{ marginBottom: 4 }}>
                      <span className="wb-design-label" style={{ display: "block", marginBottom: 4 }}>Text alignment</span>
                      <div className="wb-align-buttons" style={{ display: "flex", gap: 4 }}>
                        {(["left", "center", "right"] as const).map((align) => <button key={align} type="button" className={`wb-align-btn${String(design.text_align || "left") === align ? " active" : ""}`} style={{ flex: 1, padding: "4px 8px", fontSize: "0.75rem", fontWeight: 600, border: "1px solid var(--wb-border, #e5e5e3)", borderRadius: 4, background: String(design.text_align || "left") === align ? "var(--wb-accent, #274c42)" : "transparent", color: String(design.text_align || "left") === align ? "#fff" : "inherit", cursor: "pointer" }} onClick={() => setDesign("text_align", align === "left" ? null : align)} disabled={!canEdit}>{align.charAt(0).toUpperCase() + align.slice(1)}</button>)}
                      </div>
                    </div>
                    <div className="wb-design-row" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 8, marginBottom: 8 }}>
                      <label className="wb-design-label">Border color
                        <input type="color" value={String(design.border_color || "#e5e5e3")} onChange={(e) => setDesign("border_color", e.target.value)} disabled={!canEdit} style={{ width: "100%", height: 28, cursor: "pointer" }} />
                      </label>
                      <label className="wb-design-label">Border width (px)
                        <input type="number" min={0} max={8} value={Number(design.border_width ?? 0)} onChange={(e) => setDesign("border_width", e.target.value ? Number(e.target.value) : null)} disabled={!canEdit} placeholder="0" />
                      </label>
                    </div>
                    <div className="wb-design-row" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
                      <label className="wb-design-label">Border radius (px)
                        <input type="number" min={0} max={40} value={Number(design.border_radius ?? 0)} onChange={(e) => setDesign("border_radius", e.target.value ? Number(e.target.value) : null)} disabled={!canEdit} placeholder="0" />
                      </label>
                      <label className="wb-design-label">Box shadow
                        <select value={String(design.box_shadow || "none")} onChange={(e) => setDesign("box_shadow", e.target.value === "none" ? null : e.target.value)} disabled={!canEdit} style={{ width: "100%" }}>
                          <option value="none">None</option>
                          <option value="soft">Soft</option>
                          <option value="strong">Strong</option>
                        </select>
                      </label>
                    </div>
                    <label className="wb-design-label" style={{ marginBottom: 4, display: "block" }}>Columns
                      <select value={String(design.columns || "auto")} onChange={(e) => setDesign("columns", e.target.value === "auto" ? null : e.target.value)} disabled={!canEdit} style={{ width: "100%" }}>
                        <option value="auto">Auto</option>
                        <option value="2">2 columns</option>
                        <option value="3">3 columns</option>
                        <option value="4">4 columns</option>
                      </select>
                    </label>
                  </>; })()}
                </fieldset>

                <CssEditor value={selectedSection.content.custom_css ?? ""} disabled={!canEdit} onChange={(value) => setSections((current) => current.map((s) => s.id === selectedSection.id ? { ...s, content: { ...s.content, custom_css: value } } : s))} />
                <fieldset className="wb-design-fieldset" style={{ marginTop: 16, border: "1px solid var(--wb-border, #e5e5e3)", borderRadius: 6, padding: "12px 14px" }}>
                  <legend style={{ fontSize: "0.7rem", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--wb-muted, #6b7280)", padding: "0 6px" }}>Device visibility</legend>
                  {(["tablet", "mobile"] as const).map((target) => {
                    const overrides = brand?.[target] ?? {};
                    const hidden = (overrides.hide_section_ids ?? []).includes(selectedSection.id);
                    return <label key={target} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                      <input type="checkbox" checked={hidden} disabled={!canEdit} onChange={() => {
                        const ids: string[] = overrides.hide_section_ids ?? [];
                        const next = hidden ? ids.filter((id) => id !== selectedSection.id) : [...ids, selectedSection.id];
                        void updateBrand({ [target]: { ...overrides, hide_section_ids: next } });
                      }} />
                      Hide on {target}
                    </label>;
                  })}
                </fieldset>
                <fieldset className="wb-design-fieldset" style={{ marginTop: 16, border: "1px solid var(--wb-border, #e5e5e3)", borderRadius: 6, padding: "12px 14px" }}>
                  <legend style={{ fontSize: "0.7rem", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--wb-muted, #6b7280)", padding: "0 6px" }}>Responsive overrides</legend>
                  {(() => { const design = (selectedSection.content.design ?? {}) as Record<string, unknown>; const setDesignNested = (device: string, key: string, value: unknown) => setSections((current) => current.map((s) => { if (s.id !== selectedSection.id) return s; const d = (s.content.design ?? {}) as Record<string, unknown>; const sub = (d[device] ?? {}) as Record<string, unknown>; return { ...s, content: { ...s.content, design: { ...d, [device]: { ...sub, [key]: value } } } }; })); const tabletD = (design.tablet ?? {}) as Record<string, unknown>; const mobileD = (design.mobile ?? {}) as Record<string, unknown>; return <>
                    <p style={{ fontSize: "0.7rem", color: "var(--wb-muted, #6b7280)", margin: "0 0 8px" }}>Override design for smaller screens</p>
                    <div className="wb-design-row" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
                      <label className="wb-design-label">Tablet pad top (px)
                        <input type="number" min={0} max={200} value={Number(tabletD.padding_top ?? "")} onChange={(e) => setDesignNested("tablet", "padding_top", e.target.value ? Number(e.target.value) : null)} disabled={!canEdit} placeholder="inherit" />
                      </label>
                      <label className="wb-design-label">Tablet pad bottom (px)
                        <input type="number" min={0} max={200} value={Number(tabletD.padding_bottom ?? "")} onChange={(e) => setDesignNested("tablet", "padding_bottom", e.target.value ? Number(e.target.value) : null)} disabled={!canEdit} placeholder="inherit" />
                      </label>
                    </div>
                    <div className="wb-design-row" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
                      <label className="wb-design-label">Mobile pad top (px)
                        <input type="number" min={0} max={200} value={Number(mobileD.padding_top ?? "")} onChange={(e) => setDesignNested("mobile", "padding_top", e.target.value ? Number(e.target.value) : null)} disabled={!canEdit} placeholder="inherit" />
                      </label>
                      <label className="wb-design-label">Mobile pad bottom (px)
                        <input type="number" min={0} max={200} value={Number(mobileD.padding_bottom ?? "")} onChange={(e) => setDesignNested("mobile", "padding_bottom", e.target.value ? Number(e.target.value) : null)} disabled={!canEdit} placeholder="inherit" />
                      </label>
                    </div>
                    <div className="wb-design-row" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                      <label className="wb-design-label">Tablet font scale
                        <input type="number" min={0.7} max={1.4} step={0.05} value={Number(tabletD.font_scale ?? 1)} onChange={(e) => setDesignNested("tablet", "font_scale", Number(e.target.value) === 1 ? null : Number(e.target.value))} disabled={!canEdit} />
                      </label>
                      <label className="wb-design-label">Mobile font scale
                        <input type="number" min={0.7} max={1.4} step={0.05} value={Number(mobileD.font_scale ?? 1)} onChange={(e) => setDesignNested("mobile", "font_scale", Number(e.target.value) === 1 ? null : Number(e.target.value))} disabled={!canEdit} />
                      </label>
                    </div>
                  </>; })()}
                </fieldset>
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

            {/* ── Themes tab ── */}
            {rightTab === "themes" && website && (
              <section className="wb-panel">
                <h3>Theme instances</h3>
                <p className="wb-panel-meta">{themeInstances.length} theme{themeInstances.length !== 1 ? "s" : ""}</p>
                <div className="wb-version-list">
                  {themeInstances.map((ti) => {
                    const snap = (ti.brand_snapshot as Record<string, unknown> | null) ?? {};
                    const colors = ((snap.theme as Record<string, unknown>)?.colors ?? snap) as Record<string, string>;
                    return (
                    <div className="wb-version-row" key={ti.id} style={{ borderLeft: ti.status === "live" ? "3px solid var(--wb-accent, #274c42)" : "3px solid transparent", flexDirection: "column", gap: 6 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%" }}>
                        <div>
                          <strong>{ti.name}</strong>
                          <small style={{ textTransform: "capitalize" }}>{ti.status} · v{ti.version} · {ti.updated_at ? new Date(ti.updated_at).toLocaleDateString() : new Date(ti.created_at).toLocaleDateString()}</small>
                        </div>
                        <div style={{ display: "flex", gap: 2 }}>
                          {[colors.primary, colors.accent, colors.background].filter(Boolean).map((c, i) => (
                            <span key={i} style={{ display: "inline-block", width: 12, height: 12, borderRadius: "50%", background: c, border: "1px solid rgba(0,0,0,.12)" }} />
                          ))}
                        </div>
                      </div>
                      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                        {ti.status === "draft" && (
                          <button className="wb-btn wb-btn-primary" style={{ fontSize: "0.72rem", padding: "4px 8px" }} disabled={controlsDisabled} onClick={async () => {
                            setBusy("theme"); setError(null);
                            try {
                              await request(`/api/v1/websites/${website.id}/themes/${ti.id}/activate`, { method: "POST", headers: writeHeaders(), body: JSON.stringify({ expected_version: ti.version }) });
                              setNotice(`"${ti.name}" is now live.`);
                              void load();
                            } catch (reason) { setError(reason instanceof Error ? reason.message : "Activation failed."); }
                            finally { setBusy(null); }
                          }}>Activate</button>
                        )}
                        <button className="wb-btn wb-btn-secondary" style={{ fontSize: "0.72rem", padding: "4px 8px" }} disabled={controlsDisabled} onClick={async () => {
                          setBusy("theme"); setError(null);
                          try {
                            await updateBrand(snap as Partial<Brand>);
                            setNotice(`Loaded "${ti.name}" into the editor.`);
                          } catch (reason) { setError(reason instanceof Error ? reason.message : "Load failed."); }
                          finally { setBusy(null); }
                        }}>Load</button>
                        <button className="wb-btn wb-btn-secondary" style={{ fontSize: "0.72rem", padding: "4px 8px" }} disabled={controlsDisabled} onClick={async () => {
                          setBusy("theme"); setError(null);
                          try {
                            const created = await request<ThemeInstance>(`/api/v1/websites/${website.id}/themes`, { method: "POST", headers: writeHeaders(), body: JSON.stringify({ name: `${ti.name} (copy)`, brand_snapshot: ti.brand_snapshot }) });
                            if (created) setThemeInstances((cur) => [...cur, created]);
                            setNotice(`Duplicated "${ti.name}".`);
                          } catch (reason) { setError(reason instanceof Error ? reason.message : "Duplicate failed."); }
                          finally { setBusy(null); }
                        }}>Duplicate</button>
                        <button className="wb-btn wb-btn-secondary" style={{ fontSize: "0.72rem", padding: "4px 8px" }} disabled={controlsDisabled} onClick={async () => {
                          const newName = window.prompt("Rename theme", ti.name)?.trim();
                          if (!newName || newName === ti.name) return;
                          setBusy("theme"); setError(null);
                          try {
                            const updated = await request<ThemeInstance>(`/api/v1/websites/${website.id}/themes/${ti.id}`, { method: "PATCH", headers: writeHeaders(), body: JSON.stringify({ name: newName, expected_version: ti.version }) });
                            if (updated) setThemeInstances((cur) => cur.map((t) => t.id === ti.id ? updated : t));
                            setNotice(`Renamed to "${newName}".`);
                          } catch (reason) { setError(reason instanceof Error ? reason.message : "Rename failed."); }
                          finally { setBusy(null); }
                        }}>Rename</button>
                        {ti.status !== "live" && (
                          <button className="wb-btn wb-btn-danger" style={{ fontSize: "0.72rem", padding: "4px 8px" }} disabled={controlsDisabled} onClick={async () => {
                            setBusy("theme"); setError(null);
                            try {
                              await request(`/api/v1/websites/${website.id}/themes/${ti.id}/archive`, { method: "POST", headers: writeHeaders(), body: JSON.stringify({ expected_version: ti.version }) });
                              setThemeInstances((cur) => cur.filter((t) => t.id !== ti.id));
                              setNotice(`"${ti.name}" archived.`);
                            } catch (reason) { setError(reason instanceof Error ? reason.message : "Archive failed."); }
                            finally { setBusy(null); }
                          }}>Archive</button>
                        )}
                      </div>
                    </div>
                    );
                  })}
                </div>
                <div className="wb-field-stack" style={{ marginTop: 12, borderTop: "1px solid var(--wb-border, #e5e5e3)", paddingTop: 12 }}>
                  <label>New theme
                    <div style={{ display: "flex", gap: 6 }}>
                      <input type="text" placeholder="Theme name" value={newThemeName} onChange={(e) => setNewThemeName(e.target.value)} disabled={controlsDisabled} style={{ flex: 1 }} />
                      <button className="wb-btn wb-btn-primary" disabled={controlsDisabled || !newThemeName.trim()} onClick={async () => {
                        setBusy("theme"); setError(null);
                        try {
                          const created = await request<ThemeInstance>(`/api/v1/websites/${website.id}/themes`, { method: "POST", headers: writeHeaders(), body: JSON.stringify({ name: newThemeName.trim(), brand_snapshot: brand }) });
                          if (created) setThemeInstances((cur) => [...cur, created]);
                          setNewThemeName(""); setNotice(`Theme "${newThemeName.trim()}" created.`);
                        } catch (reason) { setError(reason instanceof Error ? reason.message : "Create failed."); }
                        finally { setBusy(null); }
                      }}>Create</button>
                    </div>
                  </label>
                  <small style={{ color: "var(--wb-muted, #999)" }}>Creates a draft copy of the current brand settings.</small>
                </div>
              </section>
            )}

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

"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { SiteFooter, SiteHeader } from "./site-chrome";
import { themeStyle } from "../site-theme";
import type { SiteBrand } from "../site-theme";
import SectionBlock from "./sections";
import type { Content, Section, PublicCatalog, ResultMedia, TemplateKey } from "./sections";

type Page = { slug: string; title: string; seo_title?: string | null; seo_description?: string | null; canonical_url?: string | null; noindex?: boolean; og_title?: string | null; og_description?: string | null; og_image_media_id?: string | null; sections: Section[] };
type Redirect = { from_path: string; to_path: string; status_code: number };
type Snapshot = { template_key?: string; brand?: SiteBrand; pages: Page[]; redirects?: Redirect[] };

function templateKey(value?: string): TemplateKey { return value === "editorial_practice" || value === "warm_studio" ? value : "calm_clinic"; }

function shadowValue(key: unknown): string | undefined { if (key === "soft") return "0 2px 12px rgba(0,0,0,0.08)"; if (key === "strong") return "0 4px 24px rgba(0,0,0,0.16)"; return undefined; }

function LeadForm({ clinicSlug }: { clinicSlug: string }) {
  const [form, setForm] = useState({ full_name: "", email: "", phone: "", notes: "", consent: false }); const [status, setStatus] = useState<"idle" | "sending" | "sent">("idle"); const [error, setError] = useState<string | null>(null);
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setStatus("sending"); setError(null); try { const response = await fetch(`/api/v1/public/sites/slug/${encodeURIComponent(clinicSlug)}/leads`, { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify(form) }); const payload = await response.json() as { error?: { message?: string } }; if (!response.ok) throw new Error(payload.error?.message ?? "We could not send your message."); setStatus("sent"); setForm({ full_name: "", email: "", phone: "", notes: "", consent: false }); } catch (reason) { setError(reason instanceof Error ? reason.message : "We could not send your message."); setStatus("idle"); } }
  return <section className="public-section public-lead-section" id="contact"><div className="public-section-heading"><p className="public-eyebrow">A FIRST HELLO</p><h2>Not ready to book?<br /><em>Start a conversation.</em></h2><p>Share a little context and the clinic team can help you find the right next step.</p></div>{status === "sent" ? <div className="public-lead-success" role="status"><strong>Thanks — your message is with the clinic.</strong><span>Someone from the team will be in touch soon.</span><button className="text-link" type="button" onClick={() => setStatus("idle")}>Send another message <span>↗</span></button></div> : <form className="public-lead-form" onSubmit={submit}><label>Full name<input required maxLength={160} value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} placeholder="Your name" /></label><label>Email <span>optional</span><input type="email" maxLength={320} value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} placeholder="you@example.com" /></label><label>Phone <span>optional</span><input maxLength={40} value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} placeholder="A number the clinic can reach" /></label><label>What can we help with?<textarea maxLength={5000} value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} placeholder="Tell us what you’re hoping to explore" rows={4} /></label><label className="public-consent"><input required type="checkbox" checked={form.consent} onChange={(event) => setForm({ ...form, consent: event.target.checked })} />I consent to the clinic using these details to respond to my enquiry.</label>{error && <p className="public-lead-error" role="alert">{error}</p>}<button className="button button-primary" type="submit" disabled={status === "sending"}>{status === "sending" ? "Sending…" : "Send enquiry"}<span>→</span></button></form>}</section>;
}

export default function PublicSite({ pageSlug }: { pageSlug?: string }) {
  const params = useParams<{ clinicSlug: string }>();
  const searchParams = useSearchParams();
  const clinicSlug = decodeURIComponent(params.clinicSlug);
  const previewToken = searchParams.get("preview_token");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [catalog, setCatalog] = useState<PublicCatalog | null>(null);
  const [testimonials, setTestimonials] = useState<Array<Record<string, unknown>>>([]);
  const [results, setResults] = useState<ResultMedia[]>([]);
  useEffect(() => { void fetch(`/api/v1/public/sites/slug/${encodeURIComponent(clinicSlug)}/results`, { cache: "no-store" }).then((response) => response.ok ? response.json() : { data: [] }).then((payload) => setResults(Array.isArray(payload.data) ? payload.data as ResultMedia[] : [])).catch(() => undefined); }, [clinicSlug]);
  useEffect(() => { void fetch(`/api/v1/public/sites/slug/${encodeURIComponent(clinicSlug)}/testimonials`, { cache: "no-store" }).then((response) => response.ok ? response.json() : { data: [] }).then((payload) => setTestimonials(Array.isArray(payload.data) ? payload.data : [])).catch(() => undefined); }, [clinicSlug]);
  const [missing, setMissing] = useState(false);
  useEffect(() => {
    setSnapshot(null); setCatalog(null); setMissing(false);
    const siteUrl = previewToken
      ? `/api/v1/public/sites/slug/${encodeURIComponent(clinicSlug)}/preview?preview_token=${encodeURIComponent(previewToken)}`
      : `/api/v1/public/sites/slug/${encodeURIComponent(clinicSlug)}`;
    void fetch(siteUrl, { cache: "no-store" }).then(async (response) => { if (!response.ok) throw new Error("missing"); const payload = await response.json(); setSnapshot(payload.data.snapshot as Snapshot); const catalogResponse = await fetch(`/api/v1/public/catalog?clinic_slug=${encodeURIComponent(clinicSlug)}&limit=100`, { cache: "no-store" }); if (catalogResponse.ok) { const catalogPayload = await catalogResponse.json(); setCatalog(catalogPayload.data as PublicCatalog); } }).catch(() => setMissing(true));
  }, [clinicSlug, previewToken]);
  const page = useMemo(() => pageSlug ? snapshot?.pages.find((item) => item.slug === pageSlug) : snapshot?.pages.find((item) => item.slug === "home") ?? snapshot?.pages[0], [snapshot, pageSlug]);
  const redirect = useMemo(() => pageSlug ? snapshot?.redirects?.find((item) => item.from_path === `/${pageSlug}`) : undefined, [snapshot, pageSlug]);
  useEffect(() => {
    if (!redirect) return;
    const target = redirect.to_path;
    if (target.startsWith("/") && !target.startsWith("//")) window.location.replace(target === "/" ? `/${clinicSlug}` : `/${clinicSlug}${target}`);
    else if (/^https?:\/\//.test(target)) window.location.replace(target);
  }, [redirect, clinicSlug]);
  useEffect(() => {
    if (!page) return;
    const previousTitle = document.title;
    const created: HTMLElement[] = [];
    const meta = (attribute: "name" | "property", key: string, content: string | null | undefined) => {
      if (!content) return;
      const element = document.createElement("meta");
      element.setAttribute(attribute, key);
      element.setAttribute("content", content);
      document.head.appendChild(element);
      created.push(element);
    };
    const title = page.seo_title || page.title;
    document.title = title;
    meta("name", "description", page.seo_description);
    meta("name", "robots", page.noindex || snapshot?.brand?.seo?.robots_index === false ? "noindex, nofollow" : "index, follow");
    meta("property", "og:title", page.og_title || title);
    meta("property", "og:description", page.og_description || page.seo_description);
    meta("property", "og:type", "website");
    const imageId = page.og_image_media_id || snapshot?.brand?.seo?.default_og_image_media_id;
    if (imageId) meta("property", "og:image", `${window.location.origin}/api/v1/public/sites/${encodeURIComponent(window.location.hostname)}/media/${imageId}`);
    if (page.canonical_url) {
      const link = document.createElement("link");
      link.rel = "canonical";
      link.href = page.canonical_url.startsWith("/") ? `${window.location.origin}${page.canonical_url}` : page.canonical_url;
      document.head.appendChild(link);
      created.push(link);
    }
    return () => { document.title = previousTitle; created.forEach((element) => element.remove()); };
  }, [page, snapshot, clinicSlug]);
  if (missing) return <main className="public-not-found"><Link className="wordmark" href="/">care<span>/</span>fully</Link><p className="public-eyebrow">PAGE NOT FOUND</p><h1>This clinic website isn&apos;t available.</h1><p>The link may be unpublished or no longer active.</p><Link className="text-link" href="/">Return to carefully <span>→</span></Link></main>;
  if (snapshot && !page && !redirect) return <main className="public-not-found"><p className="public-eyebrow">PAGE NOT FOUND</p><h1>This page isn&apos;t available.</h1><Link className="text-link" href={`/${clinicSlug}`}>Back to the clinic website <span>→</span></Link></main>;
  if (!snapshot || !page) return <main className="public-loading"><p className="public-eyebrow">LOADING CLINIC</p><p role="status">Preparing your visit…</p></main>;
  const brand = snapshot.brand ?? {};
  const template = templateKey(snapshot.template_key);
  return <main className={`public-site public-site-${template}${brand.theme ? " has-theme" : ""}`} style={themeStyle(brand)}>{previewToken && <div style={{ background: "#274c42", color: "#fff", textAlign: "center", padding: "6px 16px", fontSize: "0.8rem", fontWeight: 600, letterSpacing: "0.04em" }}>DRAFT PREVIEW</div>}<SiteHeader brand={brand} clinicSlug={clinicSlug} /><div className="public-shell"><div className="public-clinic-mark"><span className="public-eyebrow">{template.replaceAll("_", " ")}</span><span>{page.title}</span></div>{page.sections.filter((section) => section.is_visible !== false).sort((a, b) => (a.position ?? 0) - (b.position ?? 0)).map((section, index) => { const hiddenOn = [section.id && (brand.tablet?.hide_section_ids ?? []).includes(section.id) ? "hide-tablet" : "", section.id && (brand.mobile?.hide_section_ids ?? []).includes(section.id) ? "hide-mobile" : ""].filter(Boolean).join(" "); const design = section.content?.design as Record<string, unknown> | undefined; const sectionStyle: Record<string, string> = {}; if (design?.background_color) sectionStyle.backgroundColor = String(design.background_color); if (design?.background_image) sectionStyle.backgroundImage = `url(${String(design.background_image)})`; if (design?.background_image) { sectionStyle.backgroundSize = "cover"; sectionStyle.backgroundPosition = "center"; } if (design?.padding_top) sectionStyle.paddingTop = `${design.padding_top}px`; if (design?.padding_bottom) sectionStyle.paddingBottom = `${design.padding_bottom}px`; if (design?.text_align) sectionStyle.textAlign = String(design.text_align); if (design?.content_width === "narrow") sectionStyle.maxWidth = "720px"; else if (design?.content_width === "contained") sectionStyle.maxWidth = "960px"; if (design?.border_color) sectionStyle.borderColor = String(design.border_color); if (design?.border_width) { sectionStyle.borderWidth = `${design.border_width}px`; sectionStyle.borderStyle = "solid"; } if (design?.border_radius) sectionStyle.borderRadius = `${design.border_radius}px`; const shadow = shadowValue(design?.box_shadow); if (shadow) sectionStyle.boxShadow = shadow; const hasOverlay = Boolean(design?.overlay_color && design?.overlay_opacity); const block = <div style={{ position: hasOverlay ? "relative" as const : undefined, ...sectionStyle }}>{hasOverlay && <div style={{ position: "absolute", inset: 0, backgroundColor: String(design!.overlay_color), opacity: Number(design!.overlay_opacity) / 100, pointerEvents: "none" as const }} />}{typeof section.content?.custom_css === "string" && section.content.custom_css && <style>{section.content.custom_css}</style>}<SectionBlock key={`${section.section_type}-${index}`} section={section} clinicSlug={clinicSlug} template={template} catalog={catalog} testimonials={testimonials} results={results} brand={brand} /></div>; return hiddenOn ? <div key={`${section.section_type}-${index}`} className={hiddenOn}>{block}</div> : <div key={`${section.section_type}-${index}`}>{block}</div>; })}<LeadForm clinicSlug={clinicSlug} /></div><SiteFooter brand={brand} title={page.title} clinicSlug={clinicSlug} /></main>;
}

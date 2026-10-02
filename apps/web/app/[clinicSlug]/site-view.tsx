"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { SiteFooter, SiteHeader } from "./site-chrome";
import FormEmbed from "./form-embed";
import { themeStyle } from "../site-theme";
import type { SiteBrand } from "../site-theme";

type Content = {
  heading?: string;
  body?: string;
  eyebrow?: string;
  button_label?: string;
  items?: Array<Record<string, unknown>>;
  services?: Array<Record<string, unknown>>;
  doctors?: Array<Record<string, unknown>>;
  hours?: Array<Record<string, unknown>>;
  location?: string;
  address?: string;
  [key: string]: unknown;
};
type Section = { id?: string; section_type: string; content: Content; is_visible?: boolean; position?: number };
type Page = { slug: string; title: string; seo_title?: string | null; seo_description?: string | null; canonical_url?: string | null; noindex?: boolean; og_title?: string | null; og_description?: string | null; og_image_media_id?: string | null; sections: Section[] };
type Redirect = { from_path: string; to_path: string; status_code: number };
type Snapshot = { template_key?: string; brand?: SiteBrand; pages: Page[]; redirects?: Redirect[] };
type PublicCatalog = { services: Array<Record<string, unknown>>; doctors: Array<Record<string, unknown>> };

function text(value: unknown, fallback = "") { return typeof value === "string" ? value : fallback; }
function items(content: Content) { return content.items ?? content.services ?? content.doctors ?? content.hours ?? []; }
function label(item: Record<string, unknown>, ...keys: string[]) { return keys.map((key) => text(item[key])).find(Boolean) ?? ""; }

type TemplateKey = "calm_clinic" | "editorial_practice" | "warm_studio";
function templateKey(value?: string): TemplateKey { return value === "editorial_practice" || value === "warm_studio" ? value : "calm_clinic"; }

type ResultMedia = { id: string; media_kind: string; captured_on: string | null; case_ref: string; url: string };
function SectionBlock({ section, clinicSlug, template, catalog, testimonials, results, brand }: { section: Section; clinicSlug: string; template: TemplateKey; catalog: PublicCatalog | null; testimonials: Array<Record<string, unknown>>; results: ResultMedia[]; brand: SiteBrand }) {
  const content = section.content ?? {};
  const type = section.section_type.toLowerCase();
  const heading = text(content.heading);
  const body = text(content.body);
  const records = items(content);
  const dynamicRecords = type === "testimonials" ? testimonials : ["services", "service"].includes(type) ? catalog?.services ?? [] : type === "doctor_profile" || ["doctors", "doctor", "team", "care_team"].includes(type) ? catalog?.doctors ?? [] : [];
  const visibleRecords = records.length > 0 ? records : dynamicRecords;
  const style = `template-${template}`;
  const embeddedFormId = type === "lead_form" ? text(records[0]?.form_id) : "";
  if (embeddedFormId) return <FormEmbed clinicSlug={clinicSlug} formId={embeddedFormId} brand={brand} heading={heading} />;
  if (["hero", "banner"].includes(type)) return <section className={`public-hero ${style} ${template}-hero`} aria-labelledby="public-hero-heading"><div><p className="public-eyebrow">{text(content.eyebrow, "THOUGHTFUL CARE, CLOSE TO HOME")}</p><h1 id="public-hero-heading">{heading || "Care that feels considered."}</h1>{body && <p className="public-lede">{body}</p>}<Link className="button button-primary" href={`/book/${encodeURIComponent(clinicSlug)}`}>{text(content.button_label, "Book an appointment")} <span>→</span></Link></div>{template === "calm_clinic" ? <div className="public-hero-art" aria-hidden="true"><div className="public-hero-sun" /><div className="public-hero-card"><span>YOUR HEALTH, IN GOOD HANDS</span><strong>Make space for feeling well.</strong></div></div> : template === "editorial_practice" ? <div className="editorial-hero-art" aria-hidden="true"><span>01</span><div><strong>Care, edited.</strong><small>PERSONAL · PRECISE · PRESENT</small></div></div> : <div className="warm-hero-art" aria-hidden="true"><div className="warm-orb" /><span>Good care<br />starts here.</span></div>}</section>;
  if (["services", "service"].includes(type) || (records.length > 0 && type.includes("service"))) return <section className={`public-section ${style}`} id="services"><div className="public-section-heading"><p className="public-eyebrow">SERVICES</p><h2>{heading || "Care, thoughtfully delivered."}</h2>{body && <p>{body}</p>}</div><div className="public-record-grid">{visibleRecords.map((item, index) => <article className={`public-record ${style}-record`} key={`${label(item, "name", "title")}-${index}`}><span className="public-record-number">{String(index + 1).padStart(2, "0")}</span><h3>{label(item, "name", "title") || "Consultation"}</h3><p>{label(item, "description", "short_description", "body")}</p>{typeof item.id === "string" && <Link className="text-link" href={`/${clinicSlug}/services/${item.id}`}>Details <span>→</span></Link>}{label(item, "duration", "duration_minutes") && <small>{label(item, "duration", "duration_minutes")} min</small>}</article>)}</div></section>;
  if (["doctors", "doctor", "team", "care_team"].includes(type)) return <section className={`public-section ${style}`} id="care-team"><div className="public-section-heading"><p className="public-eyebrow">YOUR CARE TEAM</p><h2>{heading || "People who listen."}</h2>{body && <p>{body}</p>}</div><div className="public-record-grid public-doctors">{visibleRecords.map((item, index) => <article className={`public-record ${style}-record`} key={`${label(item, "name", "public_name")}-${index}`}><div className="public-avatar" aria-hidden="true">{label(item, "name", "public_name").slice(0, 1) || "C"}</div><h3>{label(item, "name", "public_name") || "Care professional"}</h3><p>{label(item, "specialty", "role", "bio")}</p>{typeof item.id === "string" && <Link className="text-link" href={`/${clinicSlug}/doctors/${item.id}`}>Profile <span>→</span></Link>}</article>)}</div></section>;
  if (["hours", "location", "contact"].includes(type)) return <section className={`public-section public-details ${style}`} id="visit"><div className="public-section-heading"><p className="public-eyebrow">PLAN YOUR VISIT</p><h2>{heading || "A calm place to begin."}</h2>{body && <p>{body}</p>}</div><div className="public-detail-columns"><div><h3>Hours</h3>{records.map((item, index) => <p key={index}><strong>{label(item, "day", "weekday")}</strong><span>{label(item, "hours", "open", "opens_at")} {label(item, "close", "closes_at") && `– ${label(item, "close", "closes_at")}`}</span></p>)}</div><div><h3>Location</h3><p>{text(content.location, text(content.address, "Contact the clinic for location details."))}</p></div></div></section>;
  if (type === "results") {
    const cases = Array.from(new Set(results.map((m) => m.case_ref))).map((ref) => ({ ref, before: results.find((m) => m.case_ref === ref && m.media_kind === "before"), after: results.find((m) => m.case_ref === ref && m.media_kind === "after"), singles: results.filter((m) => m.case_ref === ref) }));
    return <section className={`public-section public-record-section public-results ${style}`} id="results"><div className="public-section-heading"><p className="public-eyebrow">RESULTS</p><h2>{heading || "Real results, shared with consent."}</h2>{body && <p>{body}</p>}</div>
      {results.length === 0 ? <p className="public-results-empty">Approved before &amp; after photos will appear here.</p> : <div className="public-results-grid">{cases.map((c) => <article className="public-result-case" key={c.ref}>{c.before && c.after ? <div className="public-beforeafter"><figure><img loading="lazy" src={c.before.url} alt="Before" /><figcaption>Before</figcaption></figure><figure><img loading="lazy" src={c.after.url} alt="After" /><figcaption>After</figcaption></figure></div> : <div className="public-beforeafter single">{c.singles.map((m) => <figure key={m.id}><img loading="lazy" src={m.url} alt={m.media_kind} /><figcaption>{m.media_kind}</figcaption></figure>)}</div>}</article>)}</div>}
    </section>;
  }
  if (["testimonials", "pricing", "statistics"].includes(type)) return <section className={`public-section public-record-section public-${type} ${style}`} id={type}><div className="public-section-heading"><p className="public-eyebrow">{type.replaceAll("_", " ").toUpperCase()}</p><h2>{heading || "Evidence that care can feel different."}</h2>{body && <p>{body}</p>}</div><div className="public-record-grid">{visibleRecords.map((item, index) => <article className={`public-record ${style}-record`} key={`${label(item, "name", "title", "quote")}-${index}`}><span className="public-record-number">{String(index + 1).padStart(2, "0")}</span><h3>{label(item, "name", "title", "value", "quote") || "A considered outcome"}</h3><p>{label(item, "description", "body", "quote", "detail")}</p>{label(item, "metric", "stat", "amount") && <small>{label(item, "metric", "stat", "amount")}</small>}</article>)}</div></section>;
  return <section className={`public-section public-copy ${style}`}><p className="public-eyebrow">{text(content.eyebrow, section.section_type.replaceAll("_", " ").toUpperCase())}</p>{heading && <h2>{heading}</h2>}{body && <p>{body}</p>}{(content.button_label || type.includes("book")) && <Link className="button button-primary" href={`/book/${encodeURIComponent(clinicSlug)}`}>{text(content.button_label, "Book an appointment")} <span>→</span></Link>}</section>;
}

function LeadForm({ clinicSlug }: { clinicSlug: string }) {
  const [form, setForm] = useState({ full_name: "", email: "", phone: "", notes: "", consent: false }); const [status, setStatus] = useState<"idle" | "sending" | "sent">("idle"); const [error, setError] = useState<string | null>(null);
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setStatus("sending"); setError(null); try { const response = await fetch(`/api/v1/public/sites/slug/${encodeURIComponent(clinicSlug)}/leads`, { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify(form) }); const payload = await response.json() as { error?: { message?: string } }; if (!response.ok) throw new Error(payload.error?.message ?? "We could not send your message."); setStatus("sent"); setForm({ full_name: "", email: "", phone: "", notes: "", consent: false }); } catch (reason) { setError(reason instanceof Error ? reason.message : "We could not send your message."); setStatus("idle"); } }
  return <section className="public-section public-lead-section" id="contact"><div className="public-section-heading"><p className="public-eyebrow">A FIRST HELLO</p><h2>Not ready to book?<br /><em>Start a conversation.</em></h2><p>Share a little context and the clinic team can help you find the right next step.</p></div>{status === "sent" ? <div className="public-lead-success" role="status"><strong>Thanks — your message is with the clinic.</strong><span>Someone from the team will be in touch soon.</span><button className="text-link" type="button" onClick={() => setStatus("idle")}>Send another message <span>↗</span></button></div> : <form className="public-lead-form" onSubmit={submit}><label>Full name<input required maxLength={160} value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} placeholder="Your name" /></label><label>Email <span>optional</span><input type="email" maxLength={320} value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} placeholder="you@example.com" /></label><label>Phone <span>optional</span><input maxLength={40} value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} placeholder="A number the clinic can reach" /></label><label>What can we help with?<textarea maxLength={5000} value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} placeholder="Tell us what you’re hoping to explore" rows={4} /></label><label className="public-consent"><input required type="checkbox" checked={form.consent} onChange={(event) => setForm({ ...form, consent: event.target.checked })} />I consent to the clinic using these details to respond to my enquiry.</label>{error && <p className="public-lead-error" role="alert">{error}</p>}<button className="button button-primary" type="submit" disabled={status === "sending"}>{status === "sending" ? "Sending…" : "Send enquiry"}<span>→</span></button></form>}</section>;
}

export default function PublicSite({ pageSlug }: { pageSlug?: string }) {
  const params = useParams<{ clinicSlug: string }>();
  const clinicSlug = decodeURIComponent(params.clinicSlug);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [catalog, setCatalog] = useState<PublicCatalog | null>(null);
  const [testimonials, setTestimonials] = useState<Array<Record<string, unknown>>>([]);
  const [results, setResults] = useState<ResultMedia[]>([]);
  useEffect(() => { void fetch(`/api/v1/public/sites/slug/${encodeURIComponent(clinicSlug)}/results`, { cache: "no-store" }).then((response) => response.ok ? response.json() : { data: [] }).then((payload) => setResults(Array.isArray(payload.data) ? payload.data as ResultMedia[] : [])).catch(() => undefined); }, [clinicSlug]);
  useEffect(() => { void fetch(`/api/v1/public/sites/slug/${encodeURIComponent(clinicSlug)}/testimonials`, { cache: "no-store" }).then((response) => response.ok ? response.json() : { data: [] }).then((payload) => setTestimonials(Array.isArray(payload.data) ? payload.data : [])).catch(() => undefined); }, [clinicSlug]);
  const [missing, setMissing] = useState(false);
  useEffect(() => { setSnapshot(null); setCatalog(null); setMissing(false); void fetch(`/api/v1/public/sites/slug/${encodeURIComponent(clinicSlug)}`, { cache: "no-store" }).then(async (response) => { if (!response.ok) throw new Error("missing"); const payload = await response.json(); setSnapshot(payload.data.snapshot as Snapshot); const catalogResponse = await fetch(`/api/v1/public/catalog?clinic_slug=${encodeURIComponent(clinicSlug)}&limit=100`, { cache: "no-store" }); if (catalogResponse.ok) { const catalogPayload = await catalogResponse.json(); setCatalog(catalogPayload.data as PublicCatalog); } }).catch(() => setMissing(true)); }, [clinicSlug]);
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
  return <main className={`public-site public-site-${template}${brand.theme ? " has-theme" : ""}`} style={themeStyle(brand)}><SiteHeader brand={brand} clinicSlug={clinicSlug} /><div className="public-shell"><div className="public-clinic-mark"><span className="public-eyebrow">{template.replaceAll("_", " ")}</span><span>{page.title}</span></div>{page.sections.filter((section) => section.is_visible !== false).sort((a, b) => (a.position ?? 0) - (b.position ?? 0)).map((section, index) => { const hiddenOn = [section.id && (brand.tablet?.hide_section_ids ?? []).includes(section.id) ? "hide-tablet" : "", section.id && (brand.mobile?.hide_section_ids ?? []).includes(section.id) ? "hide-mobile" : ""].filter(Boolean).join(" "); const block = <SectionBlock key={`${section.section_type}-${index}`} section={section} clinicSlug={clinicSlug} template={template} catalog={catalog} testimonials={testimonials} results={results} brand={brand} />; return hiddenOn ? <div key={`${section.section_type}-${index}`} className={hiddenOn}>{block}</div> : block; })}<LeadForm clinicSlug={clinicSlug} /></div><SiteFooter brand={brand} title={page.title} clinicSlug={clinicSlug} /></main>;
}

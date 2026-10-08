"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
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
type Section = { id?: string; section_type: string; layout_key?: string; content: Content; is_visible?: boolean; position?: number };
type Page = { slug: string; title: string; seo_title?: string | null; seo_description?: string | null; canonical_url?: string | null; noindex?: boolean; og_title?: string | null; og_description?: string | null; og_image_media_id?: string | null; sections: Section[] };
type Redirect = { from_path: string; to_path: string; status_code: number };
type Snapshot = { template_key?: string; brand?: SiteBrand; pages: Page[]; redirects?: Redirect[] };
type Branch = { id?: string; name?: string; address?: Record<string, unknown> | string; phone?: string; timezone?: string; hours?: Array<Record<string, unknown>> };
type PublicCatalog = { services: Array<Record<string, unknown>>; doctors: Array<Record<string, unknown>>; branches?: Branch[] };

function text(value: unknown, fallback = "") { return typeof value === "string" ? value : fallback; }
function items(content: Content) { return content.items ?? content.services ?? content.doctors ?? content.hours ?? []; }
function label(item: Record<string, unknown>, ...keys: string[]) { return keys.map((key) => text(item[key])).find(Boolean) ?? ""; }

type TemplateKey = "calm_clinic" | "editorial_practice" | "warm_studio";
function templateKey(value?: string): TemplateKey { return value === "editorial_practice" || value === "warm_studio" ? value : "calm_clinic"; }

function shadowValue(key: unknown): string | undefined { if (key === "soft") return "0 2px 12px rgba(0,0,0,0.08)"; if (key === "strong") return "0 4px 24px rgba(0,0,0,0.16)"; return undefined; }

type ResultMedia = { id: string; media_kind: string; captured_on: string | null; case_ref: string; url: string };
function SectionBlock({ section, clinicSlug, template, catalog, testimonials, results, brand }: { section: Section; clinicSlug: string; template: TemplateKey; catalog: PublicCatalog | null; testimonials: Array<Record<string, unknown>>; results: ResultMedia[]; brand: SiteBrand }) {
  const content = section.content ?? {};
  const type = section.section_type.toLowerCase();
  const layout = section.layout_key ?? "default";
  const heading = text(content.heading);
  const body = text(content.body);
  const records = items(content);
  const approvedTestimonials = testimonials.filter((t) => t.status === "approved" && t.consent_confirmed !== false);
  const dynamicRecords = type === "testimonials" ? approvedTestimonials : ["services", "service"].includes(type) ? catalog?.services ?? [] : type === "doctor_profile" || ["doctors", "doctor", "team", "care_team"].includes(type) ? catalog?.doctors ?? [] : [];
  const visibleRecords = records.length > 0 ? records : dynamicRecords;
  const style = `template-${template}`;
  const embeddedFormId = type === "lead_form" ? text(records[0]?.form_id) : "";
  if (embeddedFormId) return <FormEmbed clinicSlug={clinicSlug} formId={embeddedFormId} brand={brand} heading={heading} />;
  if (["hero", "banner"].includes(type)) {
    const heroEyebrow = text(content.eyebrow, "THOUGHTFUL CARE, CLOSE TO HOME");
    const heroHeading = heading || "Care that feels considered.";
    const heroBody = body;
    const heroCta = <Link className="button button-primary" href={`/book/${encodeURIComponent(clinicSlug)}`}>{text(content.button_label, "Book an appointment")} <span>→</span></Link>;
    const templateArt = template === "calm_clinic" ? <div className="public-hero-art" aria-hidden="true"><div className="public-hero-sun" /><div className="public-hero-card"><span>YOUR HEALTH, IN GOOD HANDS</span><strong>Make space for feeling well.</strong></div></div> : template === "editorial_practice" ? <div className="editorial-hero-art" aria-hidden="true"><span>01</span><div><strong>Care, edited.</strong><small>PERSONAL · PRECISE · PRESENT</small></div></div> : <div className="warm-hero-art" aria-hidden="true"><div className="warm-orb" /><span>Good care<br />starts here.</span></div>;
    if (layout === "image") {
      const bgUrl = text(content.background_image ?? content.media_url);
      return <section className={`public-hero public-hero-image ${style}`} aria-labelledby="public-hero-heading" style={bgUrl ? { backgroundImage: `url(${bgUrl})`, backgroundSize: "cover", backgroundPosition: "center" } : undefined}><div className="public-hero-overlay" /><div><p className="public-eyebrow">{heroEyebrow}</p><h1 id="public-hero-heading">{heroHeading}</h1>{heroBody && <p className="public-lede">{heroBody}</p>}{heroCta}</div></section>;
    }
    if (layout === "video") {
      const videoUrl = text(content.video_url ?? content.url);
      const posterUrl = text(content.poster_url ?? content.poster);
      return <section className={`public-hero public-hero-video ${style}`} aria-labelledby="public-hero-heading" style={{ position: "relative", overflow: "hidden" }}>{videoUrl && <video autoPlay muted loop playsInline poster={posterUrl || undefined} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", zIndex: 0 }}><source src={videoUrl} /></video>}<div className="public-hero-overlay" /><div style={{ position: "relative", zIndex: 1 }}><p className="public-eyebrow">{heroEyebrow}</p><h1 id="public-hero-heading">{heroHeading}</h1>{heroBody && <p className="public-lede">{heroBody}</p>}{heroCta}</div></section>;
    }
    if (layout === "doctor") {
      const doc = catalog?.doctors?.[0];
      const doctorName = text(content.doctor_name) || (doc ? text(doc.public_name ?? doc.name) : "");
      const doctorSpecialty = text(content.doctor_specialty) || (doc ? text(doc.specialty ?? doc.role) : "");
      return <section className={`public-hero public-hero-doctor ${style}`} aria-labelledby="public-hero-heading"><div><p className="public-eyebrow">{heroEyebrow}</p><h1 id="public-hero-heading">{heroHeading}</h1>{heroBody && <p className="public-lede">{heroBody}</p>}{heroCta}</div><div className="public-hero-doctor-card"><div className="public-avatar public-avatar-lg" aria-hidden="true">{doctorName.slice(0, 1) || "D"}</div><h3>{doctorName || "Your doctor"}</h3>{doctorSpecialty && <p>{doctorSpecialty}</p>}</div></section>;
    }
    if (layout === "booking") {
      return <section className={`public-hero public-hero-booking ${style}`} aria-labelledby="public-hero-heading"><div><p className="public-eyebrow">{heroEyebrow}</p><h1 id="public-hero-heading">{heroHeading}</h1>{heroBody && <p className="public-lede">{heroBody}</p>}</div><div className="public-hero-booking-card"><p className="public-eyebrow">QUICK BOOK</p><Link className="button button-primary" href={`/book/${encodeURIComponent(clinicSlug)}`}>Book your appointment <span>→</span></Link><small>Select a service, provider, and time that works for you.</small></div></section>;
    }
    return <section className={`public-hero ${style} ${template}-hero`} aria-labelledby="public-hero-heading"><div><p className="public-eyebrow">{heroEyebrow}</p><h1 id="public-hero-heading">{heroHeading}</h1>{heroBody && <p className="public-lede">{heroBody}</p>}{heroCta}</div>{templateArt}</section>;
  }
  if (["services", "service"].includes(type) || (records.length > 0 && type.includes("service"))) {
    const svcHeading = <div className="public-section-heading"><p className="public-eyebrow">SERVICES</p><h2>{heading || "Care, thoughtfully delivered."}</h2>{body && <p>{body}</p>}</div>;
    const renderCard = (item: Record<string, unknown>, index: number) => <article className={`public-record ${style}-record`} key={`${label(item, "name", "title")}-${index}`}><span className="public-record-number">{String(index + 1).padStart(2, "0")}</span><h3>{label(item, "name", "title") || "Consultation"}</h3><p>{label(item, "description", "short_description", "body")}</p>{typeof item.id === "string" && <Link className="text-link" href={`/${clinicSlug}/services/${item.id}`}>Details <span>→</span></Link>}{label(item, "duration", "duration_minutes") && <small>{label(item, "duration", "duration_minutes")} min</small>}</article>;
    if (layout === "grid") return <section className={`public-section ${style}`} id="services">{svcHeading}<div className="public-record-grid public-grid-4">{visibleRecords.map(renderCard)}</div></section>;
    if (layout === "slider") return <section className={`public-section ${style}`} id="services">{svcHeading}<div className="public-record-slider" style={{ display: "flex", gap: "1rem", overflowX: "auto", scrollSnapType: "x mandatory", paddingBottom: "0.5rem" }}>{visibleRecords.map((item, index) => <div key={`${label(item, "name", "title")}-${index}`} style={{ minWidth: "280px", flex: "0 0 auto", scrollSnapAlign: "start" }}>{renderCard(item, index)}</div>)}</div></section>;
    if (layout === "featured" && visibleRecords.length > 0) { const [featured, ...rest] = visibleRecords; return <section className={`public-section ${style}`} id="services">{svcHeading}<div className="public-featured-service"><article className={`public-record public-record-featured ${style}-record`}><span className="public-record-number">★</span><h3>{label(featured, "name", "title") || "Featured service"}</h3><p>{label(featured, "description", "short_description", "body")}</p>{typeof featured.id === "string" && <Link className="text-link" href={`/${clinicSlug}/services/${featured.id}`}>Details <span>→</span></Link>}</article>{rest.length > 0 && <div className="public-record-grid">{rest.map(renderCard)}</div>}</div></section>; }
    return <section className={`public-section ${style}`} id="services">{svcHeading}<div className="public-record-grid">{visibleRecords.map(renderCard)}</div></section>;
  }
  if (["doctors", "doctor", "team", "care_team"].includes(type)) return <section className={`public-section ${style}`} id="care-team"><div className="public-section-heading"><p className="public-eyebrow">YOUR CARE TEAM</p><h2>{heading || "People who listen."}</h2>{body && <p>{body}</p>}</div><div className="public-record-grid public-doctors">{visibleRecords.map((item, index) => <article className={`public-record ${style}-record`} key={`${label(item, "name", "public_name")}-${index}`}><div className="public-avatar" aria-hidden="true">{label(item, "name", "public_name").slice(0, 1) || "C"}</div><h3>{label(item, "name", "public_name") || "Care professional"}</h3><p>{label(item, "specialty", "role", "bio")}</p>{typeof item.id === "string" && <Link className="text-link" href={`/${clinicSlug}/doctors/${item.id}`}>Profile <span>→</span></Link>}</article>)}</div></section>;
  if (["hours", "location", "contact"].includes(type)) {
    const branches = catalog?.branches ?? [];
    const branchAddress = (branch: Branch) => { const addr = branch.address; if (typeof addr === "string") return addr; if (addr && typeof addr === "object") return [addr.street, addr.city, addr.state, addr.zip].filter(Boolean).join(", "); return ""; };
    const locationText = text(content.location, text(content.address));
    const hasManualHours = records.length > 0;
    return <section className={`public-section public-details ${style}`} id="visit"><div className="public-section-heading"><p className="public-eyebrow">PLAN YOUR VISIT</p><h2>{heading || "A calm place to begin."}</h2>{body && <p>{body}</p>}</div><div className="public-detail-columns">{hasManualHours ? <div><h3>Hours</h3>{records.map((item, index) => <p key={index}><strong>{label(item, "day", "weekday")}</strong><span>{label(item, "hours", "open", "opens_at")} {label(item, "close", "closes_at") && `– ${label(item, "close", "closes_at")}`}</span></p>)}</div> : branches.length > 0 ? <div><h3>Our Locations</h3>{branches.map((branch, index) => <div key={branch.id ?? index} style={{ marginBottom: "1rem" }}><strong>{branch.name ?? "Main"}</strong>{branchAddress(branch) && <p>{branchAddress(branch)}</p>}{branch.phone && <p>{branch.phone}</p>}{branch.hours?.map((h, hi) => <p key={hi}><strong>{label(h, "day", "weekday")}</strong> <span>{label(h, "hours", "open")} {label(h, "close") && `– ${label(h, "close")}`}</span></p>)}</div>)}</div> : null}<div><h3>Location</h3>{locationText ? <p>{locationText}</p> : branches.length > 0 ? branches.map((branch, index) => <p key={branch.id ?? index}>{branch.name ? <strong>{branch.name}: </strong> : null}{branchAddress(branch) || "Contact the clinic for location details."}</p>) : <p>Contact the clinic for location details.</p>}</div></div></section>;
  }
  if (type === "results") {
    const cases = Array.from(new Set(results.map((m) => m.case_ref))).map((ref) => ({ ref, before: results.find((m) => m.case_ref === ref && m.media_kind === "before"), after: results.find((m) => m.case_ref === ref && m.media_kind === "after"), singles: results.filter((m) => m.case_ref === ref) }));
    return <section className={`public-section public-record-section public-results ${style}`} id="results"><div className="public-section-heading"><p className="public-eyebrow">RESULTS</p><h2>{heading || "Real results, shared with consent."}</h2>{body && <p>{body}</p>}</div>
      {results.length === 0 ? <p className="public-results-empty">Approved before &amp; after photos will appear here.</p> : <div className="public-results-grid">{cases.map((c) => <article className="public-result-case" key={c.ref}>{c.before && c.after ? <div className="public-beforeafter"><figure><img loading="lazy" src={c.before.url} alt="Before" /><figcaption>Before</figcaption></figure><figure><img loading="lazy" src={c.after.url} alt="After" /><figcaption>After</figcaption></figure></div> : <div className="public-beforeafter single">{c.singles.map((m) => <figure key={m.id}><img loading="lazy" src={m.url} alt={m.media_kind} /><figcaption>{m.media_kind}</figcaption></figure>)}</div>}</article>)}</div>}
    </section>;
  }
  if (["testimonials", "pricing", "statistics"].includes(type)) return <section className={`public-section public-record-section public-${type} ${style}`} id={type}><div className="public-section-heading"><p className="public-eyebrow">{type.replaceAll("_", " ").toUpperCase()}</p><h2>{heading || "Evidence that care can feel different."}</h2>{body && <p>{body}</p>}</div><div className="public-record-grid">{visibleRecords.map((item, index) => <article className={`public-record ${style}-record`} key={`${label(item, "name", "title", "quote")}-${index}`}><span className="public-record-number">{String(index + 1).padStart(2, "0")}</span><h3>{label(item, "name", "title", "value", "quote") || "A considered outcome"}</h3><p>{label(item, "description", "body", "quote", "detail")}</p>{label(item, "metric", "stat", "amount") && <small>{label(item, "metric", "stat", "amount")}</small>}</article>)}</div></section>;
  if (type === "faq") return <section className={`public-section public-faq ${style}`} id="faq"><div className="public-section-heading"><p className="public-eyebrow">{text(content.eyebrow, "FAQ")}</p><h2>{heading || "Questions we hear often."}</h2>{body && <p>{body}</p>}</div><div className="public-faq-list">{records.map((item, index) => <details key={index} className="public-faq-item"><summary>{label(item, "question", "title", "name") || `Question ${index + 1}`}</summary><div className="public-faq-answer">{label(item, "answer", "body", "description") || "Contact us for more details."}</div></details>)}</div></section>;
  if (type === "timeline" || type === "process" || type === "steps") return <section className={`public-section public-timeline ${style}`} id="process"><div className="public-section-heading"><p className="public-eyebrow">{text(content.eyebrow, "HOW IT WORKS")}</p><h2>{heading || "Your journey, step by step."}</h2>{body && <p>{body}</p>}</div><ol className="public-timeline-list">{records.map((item, index) => <li key={index} className="public-timeline-step"><span className="public-timeline-marker">{String(index + 1).padStart(2, "0")}</span><div><h3>{label(item, "title", "name", "heading") || `Step ${index + 1}`}</h3><p>{label(item, "description", "body", "detail")}</p></div></li>)}</ol></section>;
  if (type === "gallery" || type === "masonry") return <section className={`public-section public-gallery ${style}`} id="gallery"><div className="public-section-heading"><p className="public-eyebrow">{text(content.eyebrow, "GALLERY")}</p><h2>{heading || "A closer look."}</h2>{body && <p>{body}</p>}</div><div className="public-gallery-grid">{records.map((item, index) => { const src = text(item.url ?? item.image ?? item.src); const alt = text(item.alt ?? item.caption ?? item.title, `Gallery image ${index + 1}`); return src ? <figure key={index} className="public-gallery-item"><img loading="lazy" src={src} alt={alt} />{label(item, "caption", "title") && <figcaption>{label(item, "caption", "title")}</figcaption>}</figure> : null; })}</div></section>;
  if (type === "video") { const videoUrl = text(content.video_url ?? content.url); const posterUrl = text(content.poster_url ?? content.poster ?? content.image); return <section className={`public-section public-video ${style}`} id="video"><div className="public-section-heading"><p className="public-eyebrow">{text(content.eyebrow, "VIDEO")}</p><h2>{heading || "See it in action."}</h2>{body && <p>{body}</p>}</div><div className="public-video-player">{videoUrl ? <video controls preload="none" poster={posterUrl || undefined} style={{ width: "100%", maxWidth: "800px", borderRadius: "8px" }}><source src={videoUrl} /></video> : posterUrl ? <img src={posterUrl} alt={heading || "Video thumbnail"} style={{ width: "100%", maxWidth: "800px", borderRadius: "8px" }} /> : <p>No video configured for this section.</p>}</div></section>; }
  if (type === "comparison" || type === "comparison_table") return <section className={`public-section public-comparison ${style}`} id="comparison"><div className="public-section-heading"><p className="public-eyebrow">{text(content.eyebrow, "COMPARE")}</p><h2>{heading || "Side by side."}</h2>{body && <p>{body}</p>}</div><div className="public-comparison-table" style={{ overflowX: "auto" }}><table style={{ width: "100%", borderCollapse: "collapse" }}><tbody>{records.map((item, index) => <tr key={index} style={{ borderBottom: "1px solid var(--theme-border, #e5e5e3)" }}><td style={{ padding: "0.75rem 1rem", fontWeight: 600 }}>{label(item, "feature", "name", "title")}</td>{Object.entries(item).filter(([key]) => !["feature", "name", "title"].includes(key)).map(([key, value]) => <td key={key} style={{ padding: "0.75rem 1rem" }}>{String(value)}</td>)}</tr>)}</tbody></table></div></section>;
  return <section className={`public-section public-copy ${style}`}><p className="public-eyebrow">{text(content.eyebrow, section.section_type.replaceAll("_", " ").toUpperCase())}</p>{heading && <h2>{heading}</h2>}{body && <p>{body}</p>}{(content.button_label || type.includes("book")) && <Link className="button button-primary" href={`/book/${encodeURIComponent(clinicSlug)}`}>{text(content.button_label, "Book an appointment")} <span>→</span></Link>}</section>;
}

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

"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";

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
type Section = { section_type: string; content: Content; is_visible?: boolean; position?: number };
type Page = { slug: string; title: string; seo_title?: string | null; seo_description?: string | null; sections: Section[] };
type Snapshot = { template_key?: string; brand?: Record<string, string>; pages: Page[] };

function text(value: unknown, fallback = "") { return typeof value === "string" ? value : fallback; }
function items(content: Content) { return content.items ?? content.services ?? content.doctors ?? content.hours ?? []; }
function label(item: Record<string, unknown>, ...keys: string[]) { return keys.map((key) => text(item[key])).find(Boolean) ?? ""; }

type TemplateKey = "calm_clinic" | "editorial_practice" | "warm_studio";
function templateKey(value?: string): TemplateKey { return value === "editorial_practice" || value === "warm_studio" ? value : "calm_clinic"; }

function SectionBlock({ section, clinicSlug, template }: { section: Section; clinicSlug: string; template: TemplateKey }) {
  const content = section.content ?? {};
  const type = section.section_type.toLowerCase();
  const heading = text(content.heading);
  const body = text(content.body);
  const records = items(content);
  const style = `template-${template}`;
  if (["hero", "banner"].includes(type)) return <section className={`public-hero ${style} ${template}-hero`} aria-labelledby="public-hero-heading"><div><p className="public-eyebrow">{text(content.eyebrow, "THOUGHTFUL CARE, CLOSE TO HOME")}</p><h1 id="public-hero-heading">{heading || "Care that feels considered."}</h1>{body && <p className="public-lede">{body}</p>}<Link className="button button-primary" href={`/book/${encodeURIComponent(clinicSlug)}`}>{text(content.button_label, "Book an appointment")} <span>→</span></Link></div>{template === "calm_clinic" ? <div className="public-hero-art" aria-hidden="true"><div className="public-hero-sun" /><div className="public-hero-card"><span>YOUR HEALTH, IN GOOD HANDS</span><strong>Make space for feeling well.</strong></div></div> : template === "editorial_practice" ? <div className="editorial-hero-art" aria-hidden="true"><span>01</span><div><strong>Care, edited.</strong><small>PERSONAL · PRECISE · PRESENT</small></div></div> : <div className="warm-hero-art" aria-hidden="true"><div className="warm-orb" /><span>Good care<br />starts here.</span></div>}</section>;
  if (["services", "service"].includes(type) || (records.length > 0 && type.includes("service"))) return <section className={`public-section ${style}`} id="services"><div className="public-section-heading"><p className="public-eyebrow">SERVICES</p><h2>{heading || "Care, thoughtfully delivered."}</h2>{body && <p>{body}</p>}</div><div className="public-record-grid">{records.map((item, index) => <article className={`public-record ${style}-record`} key={`${label(item, "name", "title")}-${index}`}><span className="public-record-number">{String(index + 1).padStart(2, "0")}</span><h3>{label(item, "name", "title") || "Consultation"}</h3><p>{label(item, "description", "short_description", "body")}</p>{label(item, "duration", "duration_minutes") && <small>{label(item, "duration", "duration_minutes")} min</small>}</article>)}</div></section>;
  if (["doctors", "doctor", "team", "care_team"].includes(type)) return <section className={`public-section ${style}`} id="care-team"><div className="public-section-heading"><p className="public-eyebrow">YOUR CARE TEAM</p><h2>{heading || "People who listen."}</h2>{body && <p>{body}</p>}</div><div className="public-record-grid public-doctors">{records.map((item, index) => <article className={`public-record ${style}-record`} key={`${label(item, "name", "public_name")}-${index}`}><div className="public-avatar" aria-hidden="true">{label(item, "name", "public_name").slice(0, 1) || "C"}</div><h3>{label(item, "name", "public_name") || "Care professional"}</h3><p>{label(item, "specialty", "role", "bio")}</p></article>)}</div></section>;
  if (["hours", "location", "contact"].includes(type)) return <section className={`public-section public-details ${style}`} id="visit"><div className="public-section-heading"><p className="public-eyebrow">PLAN YOUR VISIT</p><h2>{heading || "A calm place to begin."}</h2>{body && <p>{body}</p>}</div><div className="public-detail-columns"><div><h3>Hours</h3>{records.map((item, index) => <p key={index}><strong>{label(item, "day", "weekday")}</strong><span>{label(item, "hours", "open", "opens_at")} {label(item, "close", "closes_at") && `– ${label(item, "close", "closes_at")}`}</span></p>)}</div><div><h3>Location</h3><p>{text(content.location, text(content.address, "Contact the clinic for location details."))}</p></div></div></section>;
  return <section className={`public-section public-copy ${style}`}><p className="public-eyebrow">{text(content.eyebrow, section.section_type.replaceAll("_", " ").toUpperCase())}</p>{heading && <h2>{heading}</h2>}{body && <p>{body}</p>}{(content.button_label || type.includes("book")) && <Link className="button button-primary" href={`/book/${encodeURIComponent(clinicSlug)}`}>{text(content.button_label, "Book an appointment")} <span>→</span></Link>}</section>;
}

export default function PublicClinicPage() {
  const params = useParams<{ clinicSlug: string }>();
  const clinicSlug = decodeURIComponent(params.clinicSlug);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [missing, setMissing] = useState(false);
  useEffect(() => { setSnapshot(null); setMissing(false); void fetch(`/api/v1/public/sites/slug/${encodeURIComponent(clinicSlug)}`, { cache: "no-store" }).then(async (response) => { if (!response.ok) throw new Error("missing"); const payload = await response.json(); setSnapshot(payload.data.snapshot as Snapshot); }).catch(() => setMissing(true)); }, [clinicSlug]);
  const page = useMemo(() => snapshot?.pages.find((item) => item.slug === "home") ?? snapshot?.pages[0], [snapshot]);
  if (missing) return <main className="public-not-found"><Link className="wordmark" href="/">care<span>/</span>fully</Link><p className="public-eyebrow">PAGE NOT FOUND</p><h1>This clinic website isn&apos;t available.</h1><p>The link may be unpublished or no longer active.</p><Link className="text-link" href="/">Return to carefully <span>→</span></Link></main>;
  if (!snapshot || !page) return <main className="public-loading"><p className="public-eyebrow">LOADING CLINIC</p><p role="status">Preparing your visit…</p></main>;
  const brand = snapshot.brand ?? {};
  const template = templateKey(snapshot.template_key);
  return <main className={`public-site public-site-${template}`} style={{ "--public-accent": brand.primary_color || "#274c42", "--public-paper": brand.background_color || "#f5f4ee" } as CSSProperties}><header className="public-header"><Link className="wordmark" href="/">care<span>/</span>fully</Link><nav aria-label="Clinic website"><a href="#services">Services</a><a href="#visit">Visit</a><Link className="button button-primary" href={`/book/${encodeURIComponent(clinicSlug)}`}>Book <span>→</span></Link></nav></header><div className="public-shell"><div className="public-clinic-mark"><span className="public-eyebrow">{template.replaceAll("_", " ")}</span><span>{page.title}</span></div>{page.sections.filter((section) => section.is_visible !== false).sort((a, b) => (a.position ?? 0) - (b.position ?? 0)).map((section, index) => <SectionBlock key={`${section.section_type}-${index}`} section={section} clinicSlug={clinicSlug} template={template} />)}</div><footer className="public-footer"><span>{page.title}</span><Link href={`/book/${encodeURIComponent(clinicSlug)}`}>Request an appointment <span>↗</span></Link></footer></main>;
}

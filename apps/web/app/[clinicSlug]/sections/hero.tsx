import Link from "next/link";
import type { SectionProps } from "./types";
import { text } from "./types";

export default function HeroSection({ section, clinicSlug, template, catalog, brand }: SectionProps) {
  const content = section.content ?? {};
  const layout = section.layout_key ?? "default";
  const heading = text(content.heading);
  const body = text(content.body);
  const style = `template-${template}`;
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

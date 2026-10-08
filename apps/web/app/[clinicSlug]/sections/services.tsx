import Link from "next/link";
import type { SectionProps } from "./types";
import { text, items, label } from "./types";

export default function ServicesSection({ section, clinicSlug, template, catalog }: SectionProps) {
  const content = section.content ?? {};
  const layout = section.layout_key ?? "default";
  const heading = text(content.heading);
  const body = text(content.body);
  const records = items(content);
  const style = `template-${template}`;
  const visibleRecords = records.length > 0 ? records : catalog?.services ?? [];

  const svcHeading = <div className="public-section-heading"><p className="public-eyebrow">SERVICES</p><h2>{heading || "Care, thoughtfully delivered."}</h2>{body && <p>{body}</p>}</div>;
  const renderCard = (item: Record<string, unknown>, index: number) => <article className={`public-record ${style}-record`} key={`${label(item, "name", "title")}-${index}`}><span className="public-record-number">{String(index + 1).padStart(2, "0")}</span><h3>{label(item, "name", "title") || "Consultation"}</h3><p>{label(item, "description", "short_description", "body")}</p>{typeof item.id === "string" && <Link className="text-link" href={`/${clinicSlug}/services/${item.id}`}>Details <span>→</span></Link>}{label(item, "duration", "duration_minutes") && <small>{label(item, "duration", "duration_minutes")} min</small>}</article>;

  if (layout === "grid") return <section className={`public-section ${style}`} id="services">{svcHeading}<div className="public-record-grid public-grid-4">{visibleRecords.map(renderCard)}</div></section>;
  if (layout === "slider") return <section className={`public-section ${style}`} id="services">{svcHeading}<div className="public-record-slider" style={{ display: "flex", gap: "1rem", overflowX: "auto", scrollSnapType: "x mandatory", paddingBottom: "0.5rem" }}>{visibleRecords.map((item, index) => <div key={`${label(item, "name", "title")}-${index}`} style={{ minWidth: "280px", flex: "0 0 auto", scrollSnapAlign: "start" }}>{renderCard(item, index)}</div>)}</div></section>;
  if (layout === "featured" && visibleRecords.length > 0) { const [featured, ...rest] = visibleRecords; return <section className={`public-section ${style}`} id="services">{svcHeading}<div className="public-featured-service"><article className={`public-record public-record-featured ${style}-record`}><span className="public-record-number">★</span><h3>{label(featured, "name", "title") || "Featured service"}</h3><p>{label(featured, "description", "short_description", "body")}</p>{typeof featured.id === "string" && <Link className="text-link" href={`/${clinicSlug}/services/${featured.id}`}>Details <span>→</span></Link>}</article>{rest.length > 0 && <div className="public-record-grid">{rest.map(renderCard)}</div>}</div></section>; }
  return <section className={`public-section ${style}`} id="services">{svcHeading}<div className="public-record-grid">{visibleRecords.map(renderCard)}</div></section>;
}

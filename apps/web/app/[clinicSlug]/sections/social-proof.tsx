import type { SectionProps } from "./types";
import { text, items, label } from "./types";

export default function SocialProofSection({ section, template, testimonials }: SectionProps) {
  const content = section.content ?? {};
  const type = section.section_type.toLowerCase();
  const heading = text(content.heading);
  const body = text(content.body);
  const records = items(content);
  const style = `template-${template}`;
  const approvedTestimonials = testimonials.filter((t) => t.status === "approved" && t.consent_confirmed !== false);
  const visibleRecords = records.length > 0 ? records : type === "testimonials" ? approvedTestimonials : [];

  return <section className={`public-section public-record-section public-${type} ${style}`} id={type}><div className="public-section-heading"><p className="public-eyebrow">{type.replaceAll("_", " ").toUpperCase()}</p><h2>{heading || "Evidence that care can feel different."}</h2>{body && <p>{body}</p>}</div><div className="public-record-grid">{visibleRecords.map((item, index) => <article className={`public-record ${style}-record`} key={`${label(item, "name", "title", "quote")}-${index}`}><span className="public-record-number">{String(index + 1).padStart(2, "0")}</span><h3>{label(item, "name", "title", "value", "quote") || "A considered outcome"}</h3><p>{label(item, "description", "body", "quote", "detail")}</p>{label(item, "metric", "stat", "amount") && <small>{label(item, "metric", "stat", "amount")}</small>}</article>)}</div></section>;
}

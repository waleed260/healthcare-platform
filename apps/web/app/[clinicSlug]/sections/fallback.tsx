import Link from "next/link";
import type { SectionProps } from "./types";
import { text } from "./types";

export default function FallbackSection({ section, clinicSlug, template }: SectionProps) {
  const content = section.content ?? {};
  const type = section.section_type.toLowerCase();
  const heading = text(content.heading);
  const body = text(content.body);
  const style = `template-${template}`;

  return <section className={`public-section public-copy ${style}`}><p className="public-eyebrow">{text(content.eyebrow, section.section_type.replaceAll("_", " ").toUpperCase())}</p>{heading && <h2>{heading}</h2>}{body && <p>{body}</p>}{(content.button_label || type.includes("book")) && <Link className="button button-primary" href={`/book/${encodeURIComponent(clinicSlug)}`}>{text(content.button_label, "Book an appointment")} <span>→</span></Link>}</section>;
}

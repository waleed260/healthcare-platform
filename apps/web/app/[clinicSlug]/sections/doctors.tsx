import Link from "next/link";
import type { SectionProps } from "./types";
import { text, items, label } from "./types";

export default function DoctorsSection({ section, clinicSlug, template, catalog }: SectionProps) {
  const content = section.content ?? {};
  const heading = text(content.heading);
  const body = text(content.body);
  const records = items(content);
  const style = `template-${template}`;
  const visibleRecords = records.length > 0 ? records : catalog?.doctors ?? [];

  return <section className={`public-section ${style}`} id="care-team"><div className="public-section-heading"><p className="public-eyebrow">YOUR CARE TEAM</p><h2>{heading || "People who listen."}</h2>{body && <p>{body}</p>}</div><div className="public-record-grid public-doctors">{visibleRecords.map((item, index) => <article className={`public-record ${style}-record`} key={`${label(item, "name", "public_name")}-${index}`}><div className="public-avatar" aria-hidden="true">{label(item, "name", "public_name").slice(0, 1) || "C"}</div><h3>{label(item, "name", "public_name") || "Care professional"}</h3><p>{label(item, "specialty", "role", "bio")}</p>{typeof item.id === "string" && <Link className="text-link" href={`/${clinicSlug}/doctors/${item.id}`}>Profile <span>→</span></Link>}</article>)}</div></section>;
}

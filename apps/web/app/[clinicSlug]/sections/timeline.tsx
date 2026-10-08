import type { SectionProps } from "./types";
import { text, items, label } from "./types";

export default function TimelineSection({ section, template }: SectionProps) {
  const content = section.content ?? {};
  const heading = text(content.heading);
  const body = text(content.body);
  const records = items(content);
  const style = `template-${template}`;

  return <section className={`public-section public-timeline ${style}`} id="process"><div className="public-section-heading"><p className="public-eyebrow">{text(content.eyebrow, "HOW IT WORKS")}</p><h2>{heading || "Your journey, step by step."}</h2>{body && <p>{body}</p>}</div><ol className="public-timeline-list">{records.map((item, index) => <li key={index} className="public-timeline-step"><span className="public-timeline-marker">{String(index + 1).padStart(2, "0")}</span><div><h3>{label(item, "title", "name", "heading") || `Step ${index + 1}`}</h3><p>{label(item, "description", "body", "detail")}</p></div></li>)}</ol></section>;
}

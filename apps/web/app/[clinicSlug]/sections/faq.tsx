import type { SectionProps } from "./types";
import { text, items, label } from "./types";

export default function FaqSection({ section, template }: SectionProps) {
  const content = section.content ?? {};
  const heading = text(content.heading);
  const body = text(content.body);
  const records = items(content);
  const style = `template-${template}`;

  return <section className={`public-section public-faq ${style}`} id="faq"><div className="public-section-heading"><p className="public-eyebrow">{text(content.eyebrow, "FAQ")}</p><h2>{heading || "Questions we hear often."}</h2>{body && <p>{body}</p>}</div><div className="public-faq-list">{records.map((item, index) => <details key={index} className="public-faq-item"><summary>{label(item, "question", "title", "name") || `Question ${index + 1}`}</summary><div className="public-faq-answer">{label(item, "answer", "body", "description") || "Contact us for more details."}</div></details>)}</div></section>;
}

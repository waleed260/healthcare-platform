import type { SectionProps } from "./types";
import { text, items, label } from "./types";

export default function ComparisonSection({ section, template }: SectionProps) {
  const content = section.content ?? {};
  const heading = text(content.heading);
  const body = text(content.body);
  const records = items(content);
  const style = `template-${template}`;

  return <section className={`public-section public-comparison ${style}`} id="comparison"><div className="public-section-heading"><p className="public-eyebrow">{text(content.eyebrow, "COMPARE")}</p><h2>{heading || "Side by side."}</h2>{body && <p>{body}</p>}</div><div className="public-comparison-table" style={{ overflowX: "auto" }}><table style={{ width: "100%", borderCollapse: "collapse" }}><tbody>{records.map((item, index) => <tr key={index} style={{ borderBottom: "1px solid var(--theme-border, #e5e5e3)" }}><td style={{ padding: "0.75rem 1rem", fontWeight: 600 }}>{label(item, "feature", "name", "title")}</td>{Object.entries(item).filter(([key]) => !["feature", "name", "title"].includes(key)).map(([key, value]) => <td key={key} style={{ padding: "0.75rem 1rem" }}>{String(value)}</td>)}</tr>)}</tbody></table></div></section>;
}

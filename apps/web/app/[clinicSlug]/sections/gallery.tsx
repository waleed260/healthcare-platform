import type { SectionProps } from "./types";
import { text, items, label } from "./types";

export default function GallerySection({ section, template }: SectionProps) {
  const content = section.content ?? {};
  const heading = text(content.heading);
  const body = text(content.body);
  const records = items(content);
  const style = `template-${template}`;

  return <section className={`public-section public-gallery ${style}`} id="gallery"><div className="public-section-heading"><p className="public-eyebrow">{text(content.eyebrow, "GALLERY")}</p><h2>{heading || "A closer look."}</h2>{body && <p>{body}</p>}</div><div className="public-gallery-grid">{records.map((item, index) => { const src = text(item.url ?? item.image ?? item.src); const alt = text(item.alt ?? item.caption ?? item.title, `Gallery image ${index + 1}`); return src ? <figure key={index} className="public-gallery-item"><img loading="lazy" src={src} alt={alt} />{label(item, "caption", "title") && <figcaption>{label(item, "caption", "title")}</figcaption>}</figure> : null; })}</div></section>;
}

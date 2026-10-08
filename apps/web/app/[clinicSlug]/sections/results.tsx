import type { SectionProps } from "./types";
import { text } from "./types";

export default function ResultsSection({ section, template, results }: SectionProps) {
  const content = section.content ?? {};
  const heading = text(content.heading);
  const body = text(content.body);
  const style = `template-${template}`;

  const cases = Array.from(new Set(results.map((m) => m.case_ref))).map((ref) => ({ ref, before: results.find((m) => m.case_ref === ref && m.media_kind === "before"), after: results.find((m) => m.case_ref === ref && m.media_kind === "after"), singles: results.filter((m) => m.case_ref === ref) }));

  return <section className={`public-section public-record-section public-results ${style}`} id="results"><div className="public-section-heading"><p className="public-eyebrow">RESULTS</p><h2>{heading || "Real results, shared with consent."}</h2>{body && <p>{body}</p>}</div>
    {results.length === 0 ? <p className="public-results-empty">Approved before &amp; after photos will appear here.</p> : <div className="public-results-grid">{cases.map((c) => <article className="public-result-case" key={c.ref}>{c.before && c.after ? <div className="public-beforeafter"><figure><img loading="lazy" src={c.before.url} alt="Before" /><figcaption>Before</figcaption></figure><figure><img loading="lazy" src={c.after.url} alt="After" /><figcaption>After</figcaption></figure></div> : <div className="public-beforeafter single">{c.singles.map((m) => <figure key={m.id}><img loading="lazy" src={m.url} alt={m.media_kind} /><figcaption>{m.media_kind}</figcaption></figure>)}</div>}</article>)}</div>}
  </section>;
}

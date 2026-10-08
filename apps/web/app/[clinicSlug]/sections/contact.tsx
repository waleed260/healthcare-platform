import type { SectionProps, Branch } from "./types";
import { text, items, label } from "./types";

export default function ContactSection({ section, template, catalog }: SectionProps) {
  const content = section.content ?? {};
  const heading = text(content.heading);
  const body = text(content.body);
  const records = items(content);
  const style = `template-${template}`;
  const branches = catalog?.branches ?? [];

  const branchAddress = (branch: Branch) => {
    const addr = branch.address;
    if (typeof addr === "string") return addr;
    if (addr && typeof addr === "object") return [addr.street, addr.city, addr.state, addr.zip].filter(Boolean).join(", ");
    return "";
  };

  const locationText = text(content.location, text(content.address));
  const hasManualHours = records.length > 0;

  return <section className={`public-section public-details ${style}`} id="visit"><div className="public-section-heading"><p className="public-eyebrow">PLAN YOUR VISIT</p><h2>{heading || "A calm place to begin."}</h2>{body && <p>{body}</p>}</div><div className="public-detail-columns">{hasManualHours ? <div><h3>Hours</h3>{records.map((item, index) => <p key={index}><strong>{label(item, "day", "weekday")}</strong><span>{label(item, "hours", "open", "opens_at")} {label(item, "close", "closes_at") && `– ${label(item, "close", "closes_at")}`}</span></p>)}</div> : branches.length > 0 ? <div><h3>Our Locations</h3>{branches.map((branch, index) => <div key={branch.id ?? index} style={{ marginBottom: "1rem" }}><strong>{branch.name ?? "Main"}</strong>{branchAddress(branch) && <p>{branchAddress(branch)}</p>}{branch.phone && <p>{branch.phone}</p>}{branch.hours?.map((h, hi) => <p key={hi}><strong>{label(h, "day", "weekday")}</strong> <span>{label(h, "hours", "open")} {label(h, "close") && `– ${label(h, "close")}`}</span></p>)}</div>)}</div> : null}<div><h3>Location</h3>{locationText ? <p>{locationText}</p> : branches.length > 0 ? branches.map((branch, index) => <p key={branch.id ?? index}>{branch.name ? <strong>{branch.name}: </strong> : null}{branchAddress(branch) || "Contact the clinic for location details."}</p>) : <p>Contact the clinic for location details.</p>}</div></div></section>;
}

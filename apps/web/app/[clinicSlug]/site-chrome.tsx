import Link from "next/link";
import { buttonClass, safeHref } from "../site-theme";
import type { FooterColumn, NavLink, SiteBrand } from "../site-theme";

const DEFAULT_NAV: NavLink[] = [{ label: "Services", href: "#services" }, { label: "Visit", href: "#visit" }, { label: "Contact", href: "#contact" }];

function NavList({ items }: { items: NavLink[] }) {
  return <>{items.map((item) => item.children?.length
    ? <details className="site-nav-group" key={`${item.label}-${item.href}`}><summary>{item.label}</summary><div>{item.children.map((child) => <a key={`${child.label}-${child.href}`} href={safeHref(child.href)}>{child.label}</a>)}</div></details>
    : <a key={`${item.label}-${item.href}`} href={safeHref(item.href)}>{item.label}</a>)}</>;
}

export function SiteHeader({ brand, clinicSlug }: { brand: SiteBrand; clinicSlug: string }) {
  const header = brand.header ?? {};
  const nav = header.nav?.length ? header.nav : DEFAULT_NAV;
  const classes = ["public-header", header.sticky === false ? "" : "is-sticky", header.transparent ? "is-transparent" : "", `mobile-${header.mobile_layout ?? "drawer"}`].filter(Boolean).join(" ");
  return <>
    {header.announcement && <div className="site-announcement" role="note">{header.announcement}</div>}
    {header.top_strip && (header.phone || Object.keys(header.social ?? {}).length > 0) && <div className="site-top-strip">{header.phone && <a href={`tel:${header.phone.replace(/[^+\d]/g, "")}`}>{header.phone}</a>}{Object.entries(header.social ?? {}).map(([name, url]) => <a key={name} href={safeHref(url)} rel="noopener noreferrer">{name}</a>)}</div>}
    <header className={classes}>
      <Link className="wordmark" href="/">care<span>/</span>fully</Link>
      <nav aria-label="Clinic website"><NavList items={nav} />{header.phone && !header.top_strip && <a href={`tel:${header.phone.replace(/[^+\d]/g, "")}`}>{header.phone}</a>}{header.show_book_cta !== false && <Link className={`button button-primary ${buttonClass(brand)}`} href={`/book/${encodeURIComponent(clinicSlug)}`}>{header.book_cta_label || "Book"} <span>→</span></Link>}</nav>
    </header>
  </>;
}

function Column({ column }: { column: FooterColumn }) {
  return <div className="site-footer-col"><h4>{column.title || column.kind.replaceAll("_", " ")}</h4>{column.body && <p>{column.body}</p>}{column.links?.map((link) => <a key={`${link.label}-${link.href}`} href={safeHref(link.href)}>{link.label}</a>)}</div>;
}

export function SiteFooter({ brand, title, clinicSlug }: { brand: SiteBrand; title: string; clinicSlug: string }) {
  const footer = brand.footer ?? {};
  return <footer className="public-footer">
    {footer.columns?.length ? <div className="site-footer-cols">{footer.columns.map((column, index) => <Column column={column} key={`${column.kind}-${index}`} />)}</div> : null}
    <div className="site-footer-base"><span>{footer.copyright || title}</span><Link href={`/book/${encodeURIComponent(clinicSlug)}`}>Request an appointment <span>↗</span></Link></div>
  </footer>;
}

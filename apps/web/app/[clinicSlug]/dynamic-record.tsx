"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { SiteFooter, SiteHeader } from "./site-chrome";
import { themeStyle } from "../site-theme";
import type { SiteBrand } from "../site-theme";

type Branch = { id: string; code: string; name: string; timezone: string; address: Record<string, string> | null; phone: string | null };
type Service = { id: string; name: string; category: string | null; short_description: string | null; duration_minutes: number; amount_minor: number | null; currency: string | null; branch_id: string };
type Doctor = { id: string; public_name: string; specialty: string | null; branch_id: string; service_id: string };
type Catalog = { clinic: { name: string }; branches: Branch[]; services: Service[]; doctors: Doctor[] };

const KINDS = ["services", "doctors", "locations"] as const;
type Kind = (typeof KINDS)[number];
const price = (service: Service) => service.amount_minor == null ? "Contact us for pricing" : new Intl.NumberFormat(undefined, { style: "currency", currency: service.currency ?? "PKR", maximumFractionDigits: 0 }).format(service.amount_minor / 100);
const unique = <T extends { id: string }>(rows: T[]) => [...new Map(rows.map((row) => [row.id, row])).values()];

export default function DynamicCrmPage({ kind: kindParam }: { kind: Kind }) {
  const params = { ...useParams<{ clinicSlug: string; id: string }>(), kind: kindParam };
  const clinicSlug = params.clinicSlug;
  const [brand, setBrand] = useState<SiteBrand>({});
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    const slug = encodeURIComponent(clinicSlug);
    void Promise.all([
      fetch(`/api/v1/public/catalog?clinic_slug=${slug}&limit=100`, { cache: "no-store" }).then((response) => response.ok ? response.json() : Promise.reject(new Error("catalog"))),
      fetch(`/api/v1/public/sites/slug/${slug}`, { cache: "no-store" }).then((response) => response.ok ? response.json() : null).catch(() => null),
    ]).then(([catalogPayload, sitePayload]) => {
      if (!active) return;
      setCatalog(catalogPayload.data as Catalog);
      setBrand((sitePayload?.data?.snapshot?.brand as SiteBrand | undefined) ?? {});
    }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [clinicSlug]);

  const kind = KINDS.find((item) => item === params.kind) as Kind | undefined;
  const view = useMemo(() => {
    if (!catalog || !kind) return null;
    const branches = unique(catalog.branches);
    const services = unique(catalog.services);
    const doctors = unique(catalog.doctors.map((row) => ({ ...row })));
    if (kind === "services") {
      const service = services.find((item) => item.id === params.id);
      if (!service) return null;
      const branchIds = new Set(catalog.services.filter((row) => row.id === service.id).map((row) => row.branch_id));
      const providerIds = new Set(catalog.doctors.filter((row) => row.service_id === service.id).map((row) => row.id));
      return { kind, title: service.name, eyebrow: service.category ?? "Service", body: service.short_description ?? "", facts: [`${service.duration_minutes} minutes`, price(service)], related: [{ heading: "Available at", links: branches.filter((branch) => branchIds.has(branch.id)).map((branch) => ({ href: `/${clinicSlug}/locations/${branch.id}`, label: branch.name })) }, { heading: "Providers", links: doctors.filter((doctor) => providerIds.has(doctor.id)).map((doctor) => ({ href: `/${clinicSlug}/doctors/${doctor.id}`, label: doctor.public_name })) }] };
    }
    if (kind === "doctors") {
      const doctor = doctors.find((item) => item.id === params.id);
      if (!doctor) return null;
      const serviceIds = new Set(catalog.doctors.filter((row) => row.id === doctor.id).map((row) => row.service_id));
      const branchIds = new Set(catalog.doctors.filter((row) => row.id === doctor.id).map((row) => row.branch_id));
      return { kind, title: doctor.public_name, eyebrow: doctor.specialty ?? "Provider", body: "", facts: [] as string[], related: [{ heading: "Services", links: services.filter((service) => serviceIds.has(service.id)).map((service) => ({ href: `/${clinicSlug}/services/${service.id}`, label: service.name })) }, { heading: "Locations", links: branches.filter((branch) => branchIds.has(branch.id)).map((branch) => ({ href: `/${clinicSlug}/locations/${branch.id}`, label: branch.name })) }] };
    }
    const branch = branches.find((item) => item.id === params.id);
    if (!branch) return null;
    const address = Object.values(branch.address ?? {}).filter(Boolean).join(", ");
    const serviceIds = new Set(catalog.services.filter((row) => row.branch_id === branch.id).map((row) => row.id));
    const providerIds = new Set(catalog.doctors.filter((row) => row.branch_id === branch.id).map((row) => row.id));
    return { kind, title: branch.name, eyebrow: "Location", body: address, facts: [branch.phone ? `Call ${branch.phone}` : "", branch.timezone].filter(Boolean), related: [{ heading: "Services here", links: services.filter((service) => serviceIds.has(service.id)).map((service) => ({ href: `/${clinicSlug}/services/${service.id}`, label: service.name })) }, { heading: "Providers here", links: doctors.filter((doctor) => providerIds.has(doctor.id)).map((doctor) => ({ href: `/${clinicSlug}/doctors/${doctor.id}`, label: doctor.public_name })) }] };
  }, [catalog, clinicSlug, kind, params.id]);

  if (!kind || failed || (catalog && !view)) return <main className="public-not-found"><p className="public-eyebrow">PAGE NOT FOUND</p><h1>This page isn&apos;t available.</h1><Link className="text-link" href={`/${clinicSlug}`}>Back to the clinic website <span>→</span></Link></main>;
  if (!catalog || !view) return <main className="public-loading"><p className="public-eyebrow" role="status">LOADING</p></main>;

  return <main className={`public-site has-theme`} style={themeStyle(brand)}>
    <SiteHeader brand={brand} clinicSlug={clinicSlug} />
    <div className="public-shell"><article className="dynamic-page">
      <p className="public-eyebrow">{view.eyebrow}</p><h1>{view.title}</h1>{view.body && <p>{view.body}</p>}
      {view.facts.length > 0 && <ul className="dynamic-facts">{view.facts.map((fact) => <li key={fact}>{fact}</li>)}</ul>}
      <Link className="button button-primary" href={`/book/${encodeURIComponent(clinicSlug)}`}>Book appointment <span>→</span></Link>
      {view.related.filter((group) => group.links.length > 0).map((group) => <section key={group.heading}><h2>{group.heading}</h2><ul className="dynamic-links">{group.links.map((link) => <li key={link.href}><Link href={link.href}>{link.label}</Link></li>)}</ul></section>)}
    </article></div>
    <SiteFooter brand={brand} title={catalog.clinic.name} clinicSlug={clinicSlug} />
  </main>;
}

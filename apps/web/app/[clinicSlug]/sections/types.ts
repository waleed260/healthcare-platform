import type { SiteBrand } from "../../site-theme";

export type Content = {
  heading?: string;
  body?: string;
  eyebrow?: string;
  button_label?: string;
  items?: Array<Record<string, unknown>>;
  services?: Array<Record<string, unknown>>;
  doctors?: Array<Record<string, unknown>>;
  hours?: Array<Record<string, unknown>>;
  location?: string;
  address?: string;
  [key: string]: unknown;
};

export type Section = { id?: string; section_type: string; layout_key?: string; content: Content; is_visible?: boolean; position?: number };
export type Branch = { id?: string; name?: string; address?: Record<string, unknown> | string; phone?: string; timezone?: string; hours?: Array<Record<string, unknown>> };
export type PublicCatalog = { services: Array<Record<string, unknown>>; doctors: Array<Record<string, unknown>>; branches?: Branch[] };
export type ResultMedia = { id: string; media_kind: string; captured_on: string | null; case_ref: string; url: string };
export type TemplateKey = "calm_clinic" | "editorial_practice" | "warm_studio";

export type SectionProps = {
  section: Section;
  clinicSlug: string;
  template: TemplateKey;
  catalog: PublicCatalog | null;
  testimonials: Array<Record<string, unknown>>;
  results: ResultMedia[];
  brand: SiteBrand;
};

export function text(value: unknown, fallback = "") { return typeof value === "string" ? value : fallback; }
export function items(content: Content) { return content.items ?? content.services ?? content.doctors ?? content.hours ?? []; }
export function label(item: Record<string, unknown>, ...keys: string[]) { return keys.map((key) => text(item[key])).find(Boolean) ?? ""; }

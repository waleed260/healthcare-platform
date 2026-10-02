import type { CSSProperties } from "react";

export type NavLink = { label: string; href: string; children?: NavLink[] };
export type ThemeSettings = {
  colors?: Partial<Record<"primary" | "secondary" | "accent" | "background" | "text" | "muted" | "border" | "success" | "error", string>>;
  typography?: { heading_font?: string; body_font?: string; button_font?: string; h1_size?: number; h2_size?: number; body_size?: number; heading_weight?: number; line_height?: number };
  buttons?: { style?: "solid" | "outline"; radius?: number; height?: number; padding_x?: number };
  layout?: { container_width?: number; section_spacing?: number; card_radius?: number; shadow?: "none" | "soft" | "strong"; gutter?: number };
  forms?: { input_style?: "boxed" | "underline" | "filled"; label_position?: "above" | "floating"; field_spacing?: number };
};
export type HeaderSettings = { nav?: NavLink[]; sticky?: boolean; transparent?: boolean; show_book_cta?: boolean; book_cta_label?: string; phone?: string | null; announcement?: string | null; top_strip?: boolean; social?: Record<string, string>; mobile_layout?: "drawer" | "stacked" | "compact" };
export type FooterColumn = { kind: string; title?: string; body?: string; links?: NavLink[] };
export type FooterSettings = { columns?: FooterColumn[]; copyright?: string; show_legal_links?: boolean };
export type DeviceOverrides = { font_scale?: number; spacing_scale?: number; hide_section_ids?: string[]; hero_mobile_media_id?: string | null };
export type SiteBrand = {
  logo_media_id?: string; primary_color?: string; accent_color?: string; text_color?: string; background_color?: string; font_pairing?: string;
  theme?: ThemeSettings; header?: HeaderSettings; footer?: FooterSettings; tablet?: DeviceOverrides; mobile?: DeviceOverrides;
};

export const FONT_STACKS: Record<string, string> = {
  system: "system-ui, -apple-system, 'Segoe UI', sans-serif",
  serif: "Fraunces, Georgia, 'Times New Roman', serif",
  sans: "'DM Sans', 'Helvetica Neue', Arial, sans-serif",
  humanist: "'Segoe UI', Optima, Candara, 'Trebuchet MS', sans-serif",
  mono: "'DM Mono', ui-monospace, monospace",
};
const SHADOWS = { none: "none", soft: "0 8px 24px rgba(0,0,0,.08)", strong: "0 16px 44px rgba(0,0,0,.2)" } as const;
const isHex = (value?: string) => /^#[0-9a-f]{6}$/i.test(value ?? "");

export function safeHref(href: string): string {
  return /^(\/|#|https:\/\/|tel:|mailto:)/.test(href) ? href : "#";
}

/** Convert the brand document into CSS custom properties; unset values fall back to the template defaults. */
export function themeStyle(brand: SiteBrand, device: "desktop" | "tablet" | "mobile" = "desktop"): CSSProperties {
  const theme = brand.theme ?? {};
  const colors = theme.colors ?? {};
  const type = theme.typography ?? {};
  const buttons = theme.buttons ?? {};
  const layout = theme.layout ?? {};
  const forms = theme.forms ?? {};
  const override = device === "desktop" ? undefined : brand[device];
  const fontScale = override?.font_scale ?? 1;
  const spaceScale = override?.spacing_scale ?? 1;
  const pick = (...values: (string | undefined)[]) => values.find(isHex);
  const vars: Record<string, string | number | undefined> = {
    "--public-accent": pick(colors.primary, brand.primary_color) ?? "#274c42",
    "--public-paper": pick(colors.background, brand.background_color) ?? "#f5f4ee",
    "--public-text": pick(colors.text, brand.text_color),
    "--public-secondary": pick(colors.secondary),
    "--public-highlight": pick(colors.accent, brand.accent_color),
    "--public-muted": pick(colors.muted),
    "--public-border": pick(colors.border),
    "--public-success": pick(colors.success),
    "--public-error": pick(colors.error),
    "--site-heading-font": FONT_STACKS[type.heading_font ?? ""],
    "--site-body-font": FONT_STACKS[type.body_font ?? ""],
    "--site-button-font": FONT_STACKS[type.button_font ?? ""],
    "--site-h1": type.h1_size ? `${Math.round(type.h1_size * fontScale)}px` : undefined,
    "--site-h2": type.h2_size ? `${Math.round(type.h2_size * fontScale)}px` : undefined,
    "--site-body-size": type.body_size ? `${Math.round(type.body_size * fontScale)}px` : undefined,
    "--site-heading-weight": type.heading_weight,
    "--site-line-height": type.line_height,
    "--site-btn-radius": buttons.radius !== undefined ? `${buttons.radius}px` : undefined,
    "--site-btn-height": buttons.height ? `${buttons.height}px` : undefined,
    "--site-btn-pad": buttons.padding_x ? `${buttons.padding_x}px` : undefined,
    "--site-container": layout.container_width ? `${layout.container_width}px` : undefined,
    "--site-section-gap": layout.section_spacing ? `${Math.round(layout.section_spacing * spaceScale)}px` : undefined,
    "--site-card-radius": layout.card_radius !== undefined ? `${layout.card_radius}px` : undefined,
    "--site-shadow": layout.shadow ? SHADOWS[layout.shadow] : undefined,
    "--site-gutter": layout.gutter ? `${layout.gutter}px` : undefined,
    "--site-field-gap": forms.field_spacing ? `${forms.field_spacing}px` : undefined,
  };
  return Object.fromEntries(Object.entries(vars).filter(([, value]) => value !== undefined)) as CSSProperties;
}

export const buttonClass = (brand: SiteBrand) => (brand.theme?.buttons?.style === "outline" ? "site-btn-outline" : "site-btn-solid");
export const inputClass = (brand: SiteBrand) => `site-input-${brand.theme?.forms?.input_style ?? "boxed"}`;

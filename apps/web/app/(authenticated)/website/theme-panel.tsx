"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SiteFooter, SiteHeader } from "../../[clinicSlug]/site-chrome";
import { themeStyle } from "../../site-theme";
import type { FooterColumn, NavLink, SiteBrand } from "../../site-theme";

type Draft = Pick<SiteBrand, "theme" | "header" | "footer" | "tablet" | "mobile">;
type Device = "desktop" | "tablet" | "mobile";
const COLOR_KEYS = ["primary", "secondary", "accent", "background", "text", "muted", "border", "success", "error"] as const;
const COLOR_DEFAULTS: Record<(typeof COLOR_KEYS)[number], string> = { primary: "#274c42", secondary: "#5b7a6f", accent: "#e77b5c", background: "#f5f4ee", text: "#1c2928", muted: "#6b7573", border: "#d9d6cc", success: "#2f7d4f", error: "#a8392f" };
const FONTS = ["system", "serif", "sans", "humanist", "mono"];
const FOOTER_KINDS = ["about", "services", "quick_links", "branches", "hours", "contact", "social", "legal", "custom"];
const WIDTH: Record<Device, string> = { desktop: "100%", tablet: "768px", mobile: "375px" };

const pickDraft = (brand: SiteBrand): Draft => ({ theme: brand.theme, header: brand.header, footer: brand.footer, tablet: brand.tablet, mobile: brand.mobile });

// eslint-disable-next-line no-unused-vars
type SaveHandler = (draft: Draft) => Promise<void>;

export default function ThemePanel({ brand, disabled, onSave }: { brand: SiteBrand; disabled: boolean; onSave: SaveHandler }) {
  const [draft, setDraft] = useState<Draft>(() => pickDraft(brand));
  const [past, setPast] = useState<Draft[]>([]);
  const [future, setFuture] = useState<Draft[]>([]);
  const [device, setDevice] = useState<Device>("desktop");
  const [state, setState] = useState<"saved" | "saving" | "dirty" | "error">("saved");
  const saved = useRef(JSON.stringify(pickDraft(brand)));
  const timer = useRef<number | null>(null);
  const onSaveRef = useRef(onSave);
  useEffect(() => { onSaveRef.current = onSave; }, [onSave]);

  const commit = useCallback((next: Draft) => {
    setPast((items) => [...items.slice(-49), draft]);
    setFuture([]);
    setDraft(next);
    setState("dirty");
  }, [draft]);
  const undo = () => { const previous = past[past.length - 1]; if (!previous) return; setPast(past.slice(0, -1)); setFuture([draft, ...future]); setDraft(previous); setState("dirty"); };
  const redo = () => { const next = future[0]; if (!next) return; setFuture(future.slice(1)); setPast([...past, draft]); setDraft(next); setState("dirty"); };

  // Autosave (blueprint §18.2): save 1.5s after the last edit.
  useEffect(() => {
    if (state !== "dirty" || disabled) return;
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(async () => {
      const serialized = JSON.stringify(draft);
      if (serialized === saved.current) { setState("saved"); return; }
      setState("saving");
      try { await onSaveRef.current(JSON.parse(serialized) as Draft); saved.current = serialized; setState("saved"); } catch { setState("error"); }
    }, 1500);
    return () => { if (timer.current) window.clearTimeout(timer.current); };
  }, [draft, state, disabled]);

  const theme = draft.theme ?? {};
  const header = draft.header ?? {};
  const footer = draft.footer ?? {};
  const setTheme = (group: keyof NonNullable<Draft["theme"]>, key: string, value: unknown) => commit({ ...draft, theme: { ...theme, [group]: { ...(theme[group] as object | undefined), [key]: value } } });
  const setHeader = (patch: Partial<NonNullable<Draft["header"]>>) => commit({ ...draft, header: { ...header, ...patch } });
  const setFooter = (patch: Partial<NonNullable<Draft["footer"]>>) => commit({ ...draft, footer: { ...footer, ...patch } });
  const setDevice_ = (target: "tablet" | "mobile", key: "font_scale" | "spacing_scale", value: number) => commit({ ...draft, [target]: { ...(draft[target] ?? {}), [key]: value } });

  const nav: NavLink[] = header.nav ?? [];
  const setNav = (items: NavLink[]) => setHeader({ nav: items });
  const columns: FooterColumn[] = footer.columns ?? [];
  const previewBrand = useMemo<SiteBrand>(() => ({ ...brand, ...draft }), [brand, draft]);
  const num = (value: string, fallback: number) => (Number.isFinite(Number(value)) && value !== "" ? Number(value) : fallback);

  return <section className="detail-card theme-panel" aria-label="Theme, header and footer">
    <div className="card-heading"><div><p className="eyebrow">THEME · HEADER · FOOTER</p><h2>Design system</h2></div><div className="theme-actions"><button className="text-control" onClick={undo} disabled={past.length === 0 || disabled}>↶ Undo</button><button className="text-control" onClick={redo} disabled={future.length === 0 || disabled}>↷ Redo</button><span className={`draft-status theme-state-${state}`} role="status">{state === "saved" ? "All changes saved" : state === "saving" ? "Saving…" : state === "error" ? "Save failed — keep editing to retry" : "Unsaved changes"}</span></div></div>

    <fieldset className="theme-group" disabled={disabled}><legend>Colors</legend><div className="brand-fields">{COLOR_KEYS.map((key) => <label key={key}>{key}<input type="color" value={theme.colors?.[key] ?? COLOR_DEFAULTS[key]} onChange={(event) => setTheme("colors", key, event.target.value)} /></label>)}</div></fieldset>

    <fieldset className="theme-group" disabled={disabled}><legend>Typography</legend><div className="brand-fields">
      {(["heading_font", "body_font", "button_font"] as const).map((key) => <label key={key}>{key.replace("_", " ")}<select value={theme.typography?.[key] ?? (key === "heading_font" ? "serif" : "sans")} onChange={(event) => setTheme("typography", key, event.target.value)}>{FONTS.map((font) => <option key={font} value={font}>{font}</option>)}</select></label>)}
      <label>H1 size<input type="number" min={28} max={96} value={theme.typography?.h1_size ?? 56} onChange={(event) => setTheme("typography", "h1_size", num(event.target.value, 56))} /></label>
      <label>H2 size<input type="number" min={20} max={64} value={theme.typography?.h2_size ?? 36} onChange={(event) => setTheme("typography", "h2_size", num(event.target.value, 36))} /></label>
      <label>Body size<input type="number" min={13} max={22} value={theme.typography?.body_size ?? 16} onChange={(event) => setTheme("typography", "body_size", num(event.target.value, 16))} /></label>
      <label>Heading weight<select value={theme.typography?.heading_weight ?? 500} onChange={(event) => setTheme("typography", "heading_weight", Number(event.target.value))}>{[300, 400, 500, 600, 700, 800].map((weight) => <option key={weight}>{weight}</option>)}</select></label>
      <label>Line height<input type="number" min={1.2} max={2.2} step={0.1} value={theme.typography?.line_height ?? 1.6} onChange={(event) => setTheme("typography", "line_height", num(event.target.value, 1.6))} /></label>
    </div></fieldset>

    <fieldset className="theme-group" disabled={disabled}><legend>Buttons, layout and forms</legend><div className="brand-fields">
      <label>Button style<select value={theme.buttons?.style ?? "solid"} onChange={(event) => setTheme("buttons", "style", event.target.value)}><option value="solid">Solid</option><option value="outline">Outline</option></select></label>
      <label>Button radius<input type="number" min={0} max={40} value={theme.buttons?.radius ?? 2} onChange={(event) => setTheme("buttons", "radius", num(event.target.value, 2))} /></label>
      <label>Button height<input type="number" min={32} max={64} value={theme.buttons?.height ?? 44} onChange={(event) => setTheme("buttons", "height", num(event.target.value, 44))} /></label>
      <label>Container width<input type="number" min={720} max={1600} step={20} value={theme.layout?.container_width ?? 1120} onChange={(event) => setTheme("layout", "container_width", num(event.target.value, 1120))} /></label>
      <label>Section spacing<input type="number" min={16} max={200} value={theme.layout?.section_spacing ?? 72} onChange={(event) => setTheme("layout", "section_spacing", num(event.target.value, 72))} /></label>
      <label>Card radius<input type="number" min={0} max={40} value={theme.layout?.card_radius ?? 4} onChange={(event) => setTheme("layout", "card_radius", num(event.target.value, 4))} /></label>
      <label>Shadow<select value={theme.layout?.shadow ?? "soft"} onChange={(event) => setTheme("layout", "shadow", event.target.value)}><option value="none">None</option><option value="soft">Soft</option><option value="strong">Strong</option></select></label>
      <label>Input style<select value={theme.forms?.input_style ?? "boxed"} onChange={(event) => setTheme("forms", "input_style", event.target.value)}><option value="boxed">Boxed</option><option value="underline">Underline</option><option value="filled">Filled</option></select></label>
      <label>Field spacing<input type="number" min={6} max={40} value={theme.forms?.field_spacing ?? 14} onChange={(event) => setTheme("forms", "field_spacing", num(event.target.value, 14))} /></label>
    </div></fieldset>

    <fieldset className="theme-group" disabled={disabled}><legend>Header</legend>
      <div className="brand-fields">
        <label>Sticky<input type="checkbox" checked={header.sticky ?? true} onChange={(event) => setHeader({ sticky: event.target.checked })} /></label>
        <label>Transparent<input type="checkbox" checked={header.transparent ?? false} onChange={(event) => setHeader({ transparent: event.target.checked })} /></label>
        <label>Book CTA<input type="checkbox" checked={header.show_book_cta ?? true} onChange={(event) => setHeader({ show_book_cta: event.target.checked })} /></label>
        <label>CTA label<input maxLength={40} value={header.book_cta_label ?? "Book appointment"} onChange={(event) => setHeader({ book_cta_label: event.target.value || "Book appointment" })} /></label>
        <label>Phone<input maxLength={40} value={header.phone ?? ""} onChange={(event) => setHeader({ phone: event.target.value || null })} placeholder="+92 300 1234567" /></label>
        <label>Announcement<input maxLength={200} value={header.announcement ?? ""} onChange={(event) => setHeader({ announcement: event.target.value || null })} /></label>
        <label>Top contact strip<input type="checkbox" checked={header.top_strip ?? false} onChange={(event) => setHeader({ top_strip: event.target.checked })} /></label>
        <label>Mobile layout<select value={header.mobile_layout ?? "drawer"} onChange={(event) => setHeader({ mobile_layout: event.target.value as "drawer" | "stacked" | "compact" })}><option value="drawer">Scrolling bar</option><option value="stacked">Stacked</option><option value="compact">Compact (CTA only)</option></select></label>
      </div>
      <p className="eyebrow">NAVIGATION</p>
      {nav.map((item, index) => <div className="theme-row" key={index}>
        <input aria-label="Label" maxLength={60} value={item.label} onChange={(event) => setNav(nav.map((entry, i) => i === index ? { ...entry, label: event.target.value } : entry))} />
        <input aria-label="Link" maxLength={500} value={item.href} onChange={(event) => setNav(nav.map((entry, i) => i === index ? { ...entry, href: event.target.value } : entry))} placeholder="/services or #contact" />
        <button className="text-control" onClick={() => setNav(nav.map((entry, i) => i === index ? { ...entry, children: [...(entry.children ?? []), { label: "Submenu", href: "#" }] } : entry))} disabled={(item.children?.length ?? 0) >= 12}>+ Submenu</button>
        <button className="text-control" onClick={() => index > 0 && setNav(nav.map((entry, i) => i === index - 1 ? nav[index] : i === index ? nav[index - 1] : entry))} disabled={index === 0}>↑</button>
        <button className="text-control" onClick={() => setNav(nav.filter((_, i) => i !== index))}>Remove</button>
        {(item.children ?? []).map((child, childIndex) => <div className="theme-row theme-subrow" key={childIndex}>
          <input aria-label="Submenu label" maxLength={60} value={child.label} onChange={(event) => setNav(nav.map((entry, i) => i === index ? { ...entry, children: entry.children?.map((c, ci) => ci === childIndex ? { ...c, label: event.target.value } : c) } : entry))} />
          <input aria-label="Submenu link" maxLength={500} value={child.href} onChange={(event) => setNav(nav.map((entry, i) => i === index ? { ...entry, children: entry.children?.map((c, ci) => ci === childIndex ? { ...c, href: event.target.value } : c) } : entry))} />
          <button className="text-control" onClick={() => setNav(nav.map((entry, i) => i === index ? { ...entry, children: entry.children?.filter((_, ci) => ci !== childIndex) } : entry))}>Remove</button>
        </div>)}
      </div>)}
      <button className="button button-secondary" onClick={() => setNav([...nav, { label: "New link", href: "#" }])} disabled={nav.length >= 12}>Add link ＋</button>
    </fieldset>

    <fieldset className="theme-group" disabled={disabled}><legend>Footer</legend>
      {columns.map((column, index) => <div className="theme-row" key={index}>
        <select aria-label="Column type" value={column.kind} onChange={(event) => setFooter({ columns: columns.map((c, i) => i === index ? { ...c, kind: event.target.value } : c) })}>{FOOTER_KINDS.map((kind) => <option key={kind} value={kind}>{kind.replace("_", " ")}</option>)}</select>
        <input aria-label="Column title" maxLength={80} value={column.title ?? ""} placeholder="Title" onChange={(event) => setFooter({ columns: columns.map((c, i) => i === index ? { ...c, title: event.target.value } : c) })} />
        <input aria-label="Column text" maxLength={600} value={column.body ?? ""} placeholder="Text" onChange={(event) => setFooter({ columns: columns.map((c, i) => i === index ? { ...c, body: event.target.value } : c) })} />
        <button className="text-control" onClick={() => index > 0 && setFooter({ columns: columns.map((c, i) => i === index - 1 ? columns[index] : i === index ? columns[index - 1] : c) })} disabled={index === 0}>↑</button>
        <button className="text-control" onClick={() => setFooter({ columns: columns.filter((_, i) => i !== index) })}>Remove</button>
      </div>)}
      <div className="brand-fields"><button className="button button-secondary" onClick={() => setFooter({ columns: [...columns, { kind: "about" }] })} disabled={columns.length >= 6}>Add column ＋</button><label>Copyright line<input maxLength={200} value={footer.copyright ?? ""} onChange={(event) => setFooter({ copyright: event.target.value })} /></label></div>
    </fieldset>

    <fieldset className="theme-group" disabled={disabled}><legend>Per-device adjustments</legend><div className="brand-fields">
      {(["tablet", "mobile"] as const).map((target) => <label key={`${target}-f`}>{target} font scale<input type="number" min={0.7} max={1.4} step={0.05} value={draft[target]?.font_scale ?? 1} onChange={(event) => setDevice_(target, "font_scale", num(event.target.value, 1))} /></label>)}
      {(["tablet", "mobile"] as const).map((target) => <label key={`${target}-s`}>{target} spacing scale<input type="number" min={0.5} max={1.5} step={0.05} value={draft[target]?.spacing_scale ?? 1} onChange={(event) => setDevice_(target, "spacing_scale", num(event.target.value, 1))} /></label>)}
    </div></fieldset>

    <div className="theme-preview-bar"><p className="eyebrow">PREVIEW</p>{(["desktop", "tablet", "mobile"] as const).map((item) => <button key={item} className={`text-control ${device === item ? "is-active" : ""}`} onClick={() => setDevice(item)} aria-pressed={device === item}>{item}</button>)}</div>
    <div className="theme-preview-frame" style={{ width: WIDTH[device] }}><div className="public-site has-theme" style={themeStyle(previewBrand, device)}><SiteHeader brand={previewBrand} clinicSlug="preview" /><div className="public-shell"><h1>Your clinic headline</h1><h2>Section heading</h2><p>Body copy shows your typography and spacing choices.</p><a className={`button button-primary ${previewBrand.theme?.buttons?.style === "outline" ? "site-btn-outline" : ""}`} href="#preview">Primary action</a></div><SiteFooter brand={previewBrand} title="Your clinic" clinicSlug="preview" /></div></div>
  </section>;
}

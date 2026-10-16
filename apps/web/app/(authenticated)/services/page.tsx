"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, errorMessage, money, patch, post } from "../_lib/client";
import Drawer from "../_lib/drawer";
import { useToast } from "../_lib/toast";
import { useConfirm } from "../_lib/confirm";
import { useClinicCurrency } from "../_lib/clinic-context";

type Service = { id: string; name: string; category: string | null; short_description: string | null; full_description: string | null; duration_minutes: number; buffer_before_minutes: number; buffer_after_minutes: number; price_mode: string; amount_minor: number | null; currency: string | null; approval_mode: string; visibility: string; status: string; version: number };
type ServiceTemplate = { id: string; name: string; category: string | null; specialty_code: string | null; duration_minutes: number; amount_minor: number | null; currency: string | null };

const CATEGORIES = ["General", "Skin", "Hair", "Dental", "Dermatology", "Laser", "Injectable", "Surgery", "Consultation", "Lab", "Imaging"];

export default function ServicesPage() {
  const clinicCurrency = useClinicCurrency();
  const toast = useToast();
  const confirm = useConfirm();

  const [permissions, setPermissions] = useState<string[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [templates, setTemplates] = useState<ServiceTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drawer, setDrawer] = useState(false);
  const [importDrawer, setImportDrawer] = useState(false);
  const [editService, setEditService] = useState<Service | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [search, setSearch] = useState("");

  const can = useCallback((p: string) => permissions.includes(p), [permissions]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const session = await api<{ permissions?: string[] }>("/api/v1/auth/me");
      const granted = session.permissions ?? [];
      setPermissions(granted);
      const has = (c: string) => granted.includes(c);
      const [svcRows, tplRows] = await Promise.all([
        has("service.read") ? api<Service[]>("/api/v1/services?limit=100") : Promise.resolve([]),
        has("service.manage") ? api<ServiceTemplate[]>("/api/v1/catalog/service-templates?limit=100").catch(() => []) : Promise.resolve([]),
      ]);
      setServices(svcRows ?? []);
      setTemplates(tplRows ?? []);
    } catch (reason) {
      setError(errorMessage(reason, "Services could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function run(action: () => Promise<unknown>, success: string, fallback: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
      toast.success(success);
      await load();
    } catch (reason) {
      toast.error(errorMessage(reason, fallback));
    } finally {
      setBusy(false);
    }
  }

  const field = (form: FormData, key: string) => String(form.get(key) ?? "").trim();

  const filtered = useMemo(() => {
    let result = services;
    if (filter !== "all") result = result.filter((s) => (s.category ?? "General").toLowerCase() === filter.toLowerCase());
    if (search) { const q = search.toLowerCase(); result = result.filter((s) => s.name.toLowerCase().includes(q) || (s.category ?? "").toLowerCase().includes(q)); }
    return result;
  }, [services, filter, search]);

  const categories = useMemo(() => Array.from(new Set(services.map((s) => s.category ?? "General"))).sort(), [services]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const mode = field(form, "price_mode");
    const amount = Math.round(Number(field(form, "amount")) * 100);
    const body: Record<string, unknown> = {
      name: field(form, "name"), category: field(form, "category") || null, short_description: field(form, "short_description") || null,
      duration_minutes: Number(field(form, "duration")), buffer_before_minutes: Number(field(form, "buffer_before") || 0), buffer_after_minutes: Number(field(form, "buffer_after") || 0),
      price_mode: mode, amount_minor: mode === "contact" ? null : amount, currency: mode === "contact" ? null : clinicCurrency,
      approval_mode: field(form, "approval_mode"), visibility: field(form, "visibility"),
    };
    if (editService) {
      void run(() => patch(`/api/v1/services/${editService.id}`, { expected_version: editService.version, ...body }), "Service updated.", "The service could not be updated.").then(() => { setEditService(null); setDrawer(false); });
    } else {
      void run(() => post("/api/v1/services", body), "Service added.", "The service could not be created.").then(() => setDrawer(false));
    }
  }

  async function toggleStatus(svc: Service) {
    const next = svc.status === "active" ? "archived" : "active";
    const ok = await confirm({ message: `${next === "archived" ? "Deactivate" : "Reactivate"} "${svc.name}"?`, danger: next === "archived" });
    if (!ok) return;
    void run(() => post(`/api/v1/services/${svc.id}/status`, { status: next }), `Service ${next === "archived" ? "deactivated" : "reactivated"}.`, "The status could not be changed.");
  }

  function importTemplate(tpl: ServiceTemplate) {
    void run(() => post("/api/v1/services/from-template", { template_id: tpl.id }), `"${tpl.name}" imported.`, "The template could not be imported.").then(() => setImportDrawer(false));
  }

  if (loading) return <main className="dash-content"><div className="dashboard-empty" role="status"><strong>Loading services...</strong></div></main>;

  return <main className="workspace-page">
    <div className="workspace-page-header">
      <div><p className="eyebrow">CLINICAL</p><h1>Services</h1><p className="workspace-page-intro">Services your clinic offers to patients.</p></div>
      <div className="header-actions" style={{ display: "flex", gap: 8 }}>
        {can("service.manage") && <button className="button button-secondary" onClick={() => setImportDrawer(true)}>Import from catalog</button>}
        {can("service.manage") && <button className="button button-primary" onClick={() => { setEditService(null); setDrawer(true); }}>Add service <span>+</span></button>}
      </div>
    </div>

    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong></div>}

    <section className="surface-card">
      <div className="pipeline-toolbar" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", flex: 1 }}>
          <input type="search" placeholder="Search services..." value={search} onChange={(e) => setSearch(e.target.value)} style={{ maxWidth: 240, padding: "6px 12px", border: "1px solid var(--border-subtle, #e5e5e3)", borderRadius: 6, fontSize: "0.85rem", background: "var(--surface-1, #fff)" }} />
          <div className="pipeline-tabs" role="tablist" style={{ fontSize: "0.78rem" }}>
            <button role="tab" aria-selected={filter === "all"} className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>All ({services.length})</button>
            {categories.map((cat) => <button key={cat} role="tab" aria-selected={filter === cat} className={filter === cat ? "active" : ""} onClick={() => setFilter(cat)}>{cat} ({services.filter((s) => (s.category ?? "General") === cat).length})</button>)}
          </div>
        </div>
      </div>

      <div className="invoice-list">
        {filtered.length === 0 && <div className="dashboard-empty"><strong>{search || filter !== "all" ? "No matching services" : "No services yet"}</strong><span>{can("service.manage") ? "Add one or import from the master catalog." : "Ask your clinic admin to add services."}</span></div>}
        {filtered.map((svc) => <article className="invoice-row" key={svc.id}>
          <div className="invoice-mark">{svc.name.slice(0, 2).toUpperCase()}</div>
          <div className="invoice-main">
            <h3>{svc.name}</h3>
            <p>{svc.category ?? "General"} · {svc.duration_minutes} min{svc.buffer_before_minutes || svc.buffer_after_minutes ? ` (${svc.buffer_before_minutes}+${svc.buffer_after_minutes} buffer)` : ""} · {svc.price_mode === "contact" || svc.amount_minor == null ? "Contact for price" : money(svc.amount_minor, svc.currency ?? clinicCurrency)}</p>
            {svc.short_description && <small style={{ color: "var(--text-muted, #6b7280)" }}>{svc.short_description}</small>}
          </div>
          <div className="invoice-actions">
            <span className={`pipeline-status status-${svc.status === "active" ? "paid" : "void"}`}>{svc.status}</span>
            <span className={`pipeline-status status-${svc.visibility === "public" ? "contacted" : "void"}`} style={{ fontSize: "0.7rem" }}>{svc.visibility}</span>
            {can("service.manage") && <>
              <button className="text-control" disabled={busy} onClick={() => { setEditService(svc); setDrawer(true); }}>Edit</button>
              <button className="text-control" disabled={busy} onClick={() => void toggleStatus(svc)}>{svc.status === "active" ? "Deactivate" : "Reactivate"}</button>
            </>}
          </div>
        </article>)}
      </div>
    </section>

    {/* ── Service Drawer ── */}
    <Drawer open={drawer} onClose={() => { setDrawer(false); setEditService(null); }} title={editService ? "Edit service" : "Add service"}>
      <form className="drawer-form" onSubmit={handleSubmit}>
        <label>Name <span style={{ color: "var(--coral)" }}>*</span><input name="name" required defaultValue={editService?.name ?? ""} /></label>
        <label>Category<select name="category" defaultValue={editService?.category ?? "General"}>{CATEGORIES.map((c) => <option key={c}>{c}</option>)}</select></label>
        <label>Short description<input name="short_description" defaultValue={editService?.short_description ?? ""} /></label>
        <label>Duration (min) <span style={{ color: "var(--coral)" }}>*</span><input name="duration" type="number" min={5} required defaultValue={editService?.duration_minutes ?? 30} /></label>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <label>Buffer before (min)<input name="buffer_before" type="number" min={0} defaultValue={editService?.buffer_before_minutes ?? 0} /></label>
          <label>Buffer after (min)<input name="buffer_after" type="number" min={0} defaultValue={editService?.buffer_after_minutes ?? 0} /></label>
        </div>
        <label>Price mode<select name="price_mode" defaultValue={editService?.price_mode ?? "exact"}><option value="exact">Fixed price</option><option value="starting_at">Starting at</option><option value="contact">Contact for price</option></select></label>
        <label>Price ({clinicCurrency})<input name="amount" type="number" step="0.01" min={0} defaultValue={editService?.amount_minor != null ? (editService.amount_minor / 100).toFixed(2) : ""} /></label>
        <label>Approval<select name="approval_mode" defaultValue={editService?.approval_mode ?? "staff_approval"}><option value="staff_approval">Staff approval</option><option value="auto_confirm">Auto-confirm</option></select></label>
        <label>Visibility<select name="visibility" defaultValue={editService?.visibility ?? "public"}><option value="public">Public</option><option value="hidden">Hidden</option></select></label>
        <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving..." : editService ? "Update" : "Create"}</button>
      </form>
    </Drawer>

    {/* ── Import Drawer ── */}
    <Drawer open={importDrawer} onClose={() => setImportDrawer(false)} title="Import from catalog">
      {templates.length === 0 ? <div className="dashboard-empty"><strong>No templates available</strong><span>Templates appear here based on your clinic specialties.</span></div> : <div className="invoice-list">
        {templates.map((tpl) => <article className="invoice-row" key={tpl.id} style={{ cursor: "pointer" }} onClick={() => importTemplate(tpl)}>
          <div className="invoice-mark">{tpl.name.slice(0, 2).toUpperCase()}</div>
          <div className="invoice-main">
            <h3>{tpl.name}</h3>
            <p>{tpl.category ?? "General"} · {tpl.duration_minutes} min{tpl.amount_minor != null ? ` · ${money(tpl.amount_minor, tpl.currency ?? clinicCurrency)}` : ""}</p>
          </div>
        </article>)}
      </div>}
    </Drawer>
  </main>;
}

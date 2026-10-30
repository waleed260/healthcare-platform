"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, errorMessage, money, patch, post, writeHeaders } from "../_lib/client";
import Drawer from "../_lib/drawer";
import { useToast } from "../_lib/toast";
import { useConfirm } from "../_lib/confirm";
import { useClinicCurrency } from "../_lib/clinic-context";
import DataTable, { type Column } from "../_lib/data-table";

type Service = { id: string; name: string; category: string | null; short_description: string | null; full_description: string | null; duration_minutes: number; buffer_before_minutes: number; buffer_after_minutes: number; price_mode: string; amount_minor: number | null; currency: string | null; approval_mode: string; visibility: string; status: string; version: number };
type ServiceTemplate = { id: string; name: string; category: string | null; specialty_code: string | null; duration_minutes: number; amount_minor: number | null; currency: string | null };
type MaterialLink = { id: string; inventory_product_id: string; product_name: string; product_type: string; unit: string; default_quantity: number; notes: string | null };
type InvProduct = { id: string; name: string; product_type: string; unit: string; status: string };

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

  const [materials, setMaterials] = useState<MaterialLink[]>([]);
  const [invProducts, setInvProducts] = useState<InvProduct[]>([]);
  const [matBusy, setMatBusy] = useState(false);

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

  useEffect(() => {
    void api<InvProduct[]>("/api/v1/inventory/products?limit=100").then((d) => setInvProducts((d ?? []).filter((p) => p.status === "active"))).catch(() => {});
  }, []);

  useEffect(() => {
    if (!editService) { setMaterials([]); return; }
    void api<MaterialLink[]>(`/api/v1/services/${editService.id}/materials`).then((d) => setMaterials(d ?? [])).catch(() => setMaterials([]));
  }, [editService]);

  async function addMaterial(serviceId: string, productId: string) {
    setMatBusy(true);
    try {
      await post(`/api/v1/services/${serviceId}/materials`, { inventory_product_id: productId, default_quantity: 1 });
      const fresh = await api<MaterialLink[]>(`/api/v1/services/${serviceId}/materials`);
      setMaterials(fresh ?? []);
      toast.success("Material linked.");
    } catch (reason) { toast.error(errorMessage(reason, "Could not link material.")); }
    finally { setMatBusy(false); }
  }

  async function removeMaterial(serviceId: string, productId: string) {
    setMatBusy(true);
    try {
      await api(`/api/v1/services/${serviceId}/materials/${productId}`, { method: "DELETE", headers: writeHeaders() });
      setMaterials((prev) => prev.filter((m) => m.inventory_product_id !== productId));
      toast.success("Material removed.");
    } catch (reason) { toast.error(errorMessage(reason, "Could not remove material.")); }
    finally { setMatBusy(false); }
  }

  async function updateMaterialQty(serviceId: string, productId: string, qty: number) {
    if (qty <= 0 || !isFinite(qty)) return;
    setMatBusy(true);
    try {
      await patch(`/api/v1/services/${serviceId}/materials/${productId}`, { default_quantity: qty });
      setMaterials((prev) => prev.map((m) => m.inventory_product_id === productId ? { ...m, default_quantity: qty } : m));
      toast.success("Quantity updated.");
    } catch (reason) { toast.error(errorMessage(reason, "Could not update quantity.")); }
    finally { setMatBusy(false); }
  }

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

  const serviceCols: Column<Service>[] = [
    { key: "mark", header: "", width: "42px", srOnly: true, render: (svc) => <div className="invoice-mark">{svc.name.slice(0, 2).toUpperCase()}</div> },
    { key: "service", header: "Service", width: "1fr", sortable: true, sortFn: (a, b) => a.name.localeCompare(b.name), render: (svc) => (
      <div className="invoice-main">
        <h3>{svc.name}</h3>
        <p>{svc.category ?? "General"} · {svc.duration_minutes} min{svc.buffer_before_minutes || svc.buffer_after_minutes ? ` (${svc.buffer_before_minutes}+${svc.buffer_after_minutes} buffer)` : ""} · {svc.price_mode === "contact" || svc.amount_minor == null ? "Contact for price" : money(svc.amount_minor, svc.currency ?? clinicCurrency)}</p>
        {svc.short_description && <small className="svc-description">{svc.short_description}</small>}
      </div>
    )},
    { key: "status", header: "Status", width: "auto", render: (svc) => (
      <div className="invoice-actions">
        <span className={`pipeline-status status-${svc.status === "active" ? "paid" : "void"}`}>{svc.status}</span>
        <span className={`pipeline-status svc-visibility status-${svc.visibility === "public" ? "contacted" : "void"}`}>{svc.visibility}</span>
        {can("service.manage") && <>
          <button className="text-control" disabled={busy} onClick={(e) => { e.stopPropagation(); setEditService(svc); setDrawer(true); }}>Edit</button>
          <button className="text-control" disabled={busy} onClick={(e) => { e.stopPropagation(); void toggleStatus(svc); }}>{svc.status === "active" ? "Deactivate" : "Reactivate"}</button>
        </>}
      </div>
    )},
  ];

  return <main className="dash-content">
    <div className="dash-topline">
      <div><h1>Services</h1></div>
      <div className="header-actions">
        {can("service.manage") && <button className="button button-secondary" onClick={() => setImportDrawer(true)}>Import from catalog</button>}
        {can("service.manage") && <button className="button button-primary" onClick={() => { setEditService(null); setDrawer(true); }}>Add service <span>+</span></button>}
      </div>
    </div>

    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong></div>}

    <section className="surface-card">
      <div className="pipeline-toolbar svc-toolbar">
        <div className="svc-toolbar-inner">
          <input type="search" className="svc-search" placeholder="Search services..." value={search} onChange={(e) => setSearch(e.target.value)} />
          <div className="pipeline-tabs" role="tablist">
            <button role="tab" aria-selected={filter === "all"} className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>All ({services.length})</button>
            {categories.map((cat) => <button key={cat} role="tab" aria-selected={filter === cat} className={filter === cat ? "active" : ""} onClick={() => setFilter(cat)}>{cat} ({services.filter((s) => (s.category ?? "General") === cat).length})</button>)}
          </div>
        </div>
      </div>

      <DataTable
        columns={serviceCols}
        rows={filtered}
        rowKey={(s) => s.id}
        loading={loading}
        skeletonRows={5}
        emptyTitle={search || filter !== "all" ? "No matching services" : "No services yet"}
        emptyBody={can("service.manage") ? "Add one or import from the master catalog." : "Ask your clinic admin to add services."}
      />
    </section>

    <Drawer open={drawer} onClose={() => { setDrawer(false); setEditService(null); }} title={editService ? "Edit service" : "Add service"}>
      <form className="drawer-form" onSubmit={handleSubmit}>
        <label>Name <span className="svc-required">*</span><input name="name" required defaultValue={editService?.name ?? ""} /></label>
        <label>Category<select name="category" defaultValue={editService?.category ?? "General"}>{CATEGORIES.map((c) => <option key={c}>{c}</option>)}</select></label>
        <label>Short description<input name="short_description" defaultValue={editService?.short_description ?? ""} /></label>
        <label>Duration (min) <span className="svc-required">*</span><input name="duration" type="number" min={5} required defaultValue={editService?.duration_minutes ?? 30} /></label>
        <div className="svc-buffer-grid">
          <label>Buffer before (min)<input name="buffer_before" type="number" min={0} defaultValue={editService?.buffer_before_minutes ?? 0} /></label>
          <label>Buffer after (min)<input name="buffer_after" type="number" min={0} defaultValue={editService?.buffer_after_minutes ?? 0} /></label>
        </div>
        <label>Price mode<select name="price_mode" defaultValue={editService?.price_mode ?? "exact"}><option value="exact">Fixed price</option><option value="starting_at">Starting at</option><option value="contact">Contact for price</option></select></label>
        <label>Price ({clinicCurrency})<input name="amount" type="number" step="0.01" min={0} defaultValue={editService?.amount_minor != null ? (editService.amount_minor / 100).toFixed(2) : ""} /></label>
        <label>Approval<select name="approval_mode" defaultValue={editService?.approval_mode ?? "staff_approval"}><option value="staff_approval">Staff approval</option><option value="auto_confirm">Auto-confirm</option></select></label>
        <label>Visibility<select name="visibility" defaultValue={editService?.visibility ?? "public"}><option value="public">Public</option><option value="hidden">Hidden</option></select></label>

        {editService && (
          <div className="svc-materials">
            <p className="eyebrow">REQUIRED MATERIALS ({materials.length})</p>
            {materials.length === 0 && <p className="svc-materials-empty">No materials linked. Link inventory products that this service uses.</p>}
            {materials.map((m) => (
              <div key={m.id} className="svc-mat-row">
                <span className="svc-mat-name"><strong>{m.product_name}</strong> <span className="svc-mat-meta">· {m.product_type} · {m.unit}</span></span>
                <span className="svc-mat-controls">
                  <span className="svc-mat-meta">×</span>
                  <input type="number" step="any" min="0.001" defaultValue={m.default_quantity} disabled={matBusy} className="svc-mat-qty" onBlur={(e) => { const v = parseFloat(e.target.value); if (v > 0 && v !== m.default_quantity) void updateMaterialQty(editService.id, m.inventory_product_id, v); else e.target.value = String(m.default_quantity); }} onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
                  <button className="ghost-button svc-mat-remove" type="button" disabled={matBusy} onClick={() => void removeMaterial(editService.id, m.inventory_product_id)}>Remove</button>
                </span>
              </div>
            ))}
            {invProducts.length > 0 && (
              <select className="svc-mat-add" disabled={matBusy} value="" onChange={(e) => { if (e.target.value) void addMaterial(editService.id, e.target.value); }}>
                <option value="">+ Add material from inventory...</option>
                {invProducts.filter((p) => !materials.some((m) => m.inventory_product_id === p.id)).map((p) => <option key={p.id} value={p.id}>{p.name} ({p.product_type} · {p.unit})</option>)}
              </select>
            )}
          </div>
        )}

        <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving..." : editService ? "Update" : "Create"}</button>
      </form>
    </Drawer>

    <Drawer open={importDrawer} onClose={() => setImportDrawer(false)} title="Import from catalog">
      {templates.length === 0 ? <div className="dashboard-empty"><strong>No templates available</strong><span>Templates appear here based on your clinic specialties.</span></div> : <div className="invoice-list">
        {templates.map((tpl) => <article className="invoice-row dt-clickable" key={tpl.id} onClick={() => importTemplate(tpl)}>
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

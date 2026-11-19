"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, errorMessage, money, post, writeHeaders } from "../_lib/client";
import Drawer from "../_lib/drawer";
import { useToast } from "../_lib/toast";
import { useConfirm } from "../_lib/confirm";
import { useClinicCurrency } from "../_lib/clinic-context";

type Session = { permissions?: string[] };
type Package = { id: string; name: string; description: string | null; total_price_minor: number; original_value_minor: number | null; currency: string; validity_days: number; status: string; version: number; total_sessions: number };
type Service = { id: string; name: string; duration_minutes: number; amount_minor: number | null; currency: string | null };
type Patient = { id: string; full_name: string; patient_number: string };
type PatientPackage = { id: string; name: string; purchased_at: string; expires_at: string; status: string; total_sessions: number; used_sessions: number; remaining_sessions: number };
type Overview = { active_definitions: number; inactive_definitions: number; total_sold: number; active_patient_packages: number; sessions_purchased: number; sessions_used: number; sessions_remaining: number; expiring_30d: number };
type PackageService = { service_id: string; name: string; sessions_count: number };
type PackageDetail = Package & { services: PackageService[]; sold: { total_sold: number; active_count: number } };
type SessionRow = { id: string; service_id: string | null; service_name: string | null; appointment_id: string | null; status: string; override_reason: string | null; used_at: string | null; created_at: string };
type PurchaseDetail = PatientPackage & { sessions: SessionRow[] };

const put = <T,>(url: string, body: unknown) => api<T>(url, { method: "PUT", headers: writeHeaders(), body: JSON.stringify(body) });
const del = <T,>(url: string) => api<T>(url, { method: "DELETE", headers: writeHeaders() });

export default function PackagesPage() {
  const clinicCurrency = useClinicCurrency();
  const [permissions, setPermissions] = useState<string[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [packages, setPackages] = useState<Package[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [createDrawer, setCreateDrawer] = useState(false);
  const [manage, setManage] = useState<PackageDetail | null>(null);
  const [sellPkg, setSellPkg] = useState<Package | null>(null);
  const [sellKey, setSellKey] = useState<string>("");
  const [sellMode, setSellMode] = useState<"none" | "create" | "link">("none");
  const [collectNow, setCollectNow] = useState(false);
  const [patientLookup, setPatientLookup] = useState<string>("");
  const [patientPackages, setPatientPackages] = useState<PatientPackage[]>([]);
  const [purchase, setPurchase] = useState<PurchaseDetail | null>(null);

  const toast = useToast();
  const confirm = useConfirm();
  const can = useCallback((p: string) => permissions.includes(p), [permissions]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [session, over, pkgRows, svcRows, patRows] = await Promise.all([
        api<Session>("/api/v1/auth/me"),
        api<Overview>("/api/v1/packages/overview").catch(() => null),
        api<Package[]>("/api/v1/packages"),
        api<Service[]>("/api/v1/services?limit=100").catch(() => []),
        api<Patient[]>("/api/v1/patients?limit=50").catch(() => []),
      ]);
      setPermissions(session.permissions ?? []);
      setOverview(over);
      setPackages(pkgRows ?? []);
      setServices(svcRows ?? []);
      setPatients(patRows ?? []);
    } catch (reason) {
      setError(errorMessage(reason, "Packages could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const refreshManage = useCallback(async (id: string) => {
    try { setManage(await api<PackageDetail>(`/api/v1/packages/${id}`)); }
    catch (reason) { toast.error(errorMessage(reason, "The package could not be loaded.")); }
  }, [toast]);

  const refreshPatient = useCallback(async (patientId: string) => {
    try { setPatientPackages(await api<PatientPackage[]>(`/api/v1/packages/patients/${patientId}`)); }
    catch (reason) { toast.error(errorMessage(reason, "Patient packages could not be loaded.")); setPatientPackages([]); }
  }, [toast]);

  async function run(action: () => Promise<unknown>, success: string, fallback: string): Promise<boolean> {
    setBusy(true);
    try {
      await action();
      toast.success(success);
      return true;
    } catch (reason) {
      toast.error(errorMessage(reason, fallback));
      return false;
    } finally {
      setBusy(false);
    }
  }

  const field = (form: FormData, key: string) => String(form.get(key) ?? "").trim();

  function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const original = field(form, "original_price") ? Math.round(Number(field(form, "original_price")) * 100) : null;
    void run(() => post("/api/v1/packages", {
      name: field(form, "name"),
      description: field(form, "description") || null,
      total_price_minor: Math.round(Number(field(form, "price")) * 100),
      original_value_minor: original,
      currency: clinicCurrency,
      validity_days: Number(field(form, "validity_days")),
    }), "Package created.", "The package could not be created.").then((ok) => { if (ok) { setCreateDrawer(false); void load(); } });
  }

  function handleEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!manage) return;
    const form = new FormData(event.currentTarget);
    void run(() => put(`/api/v1/packages/${manage.id}`, {
      name: field(form, "name"),
      description: field(form, "description") || null,
      total_price_minor: Math.round(Number(field(form, "price")) * 100),
      original_value_minor: field(form, "original_price") ? Math.round(Number(field(form, "original_price")) * 100) : null,
      validity_days: Number(field(form, "validity_days")),
      expected_version: manage.version,
    }), "Package updated.", "The package could not be updated.").then((ok) => { if (ok) { void refreshManage(manage.id); void load(); } });
  }

  function changeStatus(action: "activate" | "deactivate" | "archive" | "unarchive") {
    if (!manage) return;
    void run(() => post(`/api/v1/packages/${manage.id}/status`, { action, expected_version: manage.version }),
      `Package ${action}d.`, `The package could not be ${action}d.`).then((ok) => {
        if (ok) { if (action === "archive") setManage(null); else void refreshManage(manage.id); void load(); }
      });
  }

  async function confirmArchive() {
    const ok = await confirm({ title: `Archive ${manage?.name}`, message: "Archived packages can no longer be sold. Existing patient purchases keep their sessions and history.", danger: true, confirmLabel: "Archive" });
    if (ok) changeStatus("archive");
  }

  function handleAddService(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!manage) return;
    const form = new FormData(event.currentTarget);
    void run(() => post(`/api/v1/packages/${manage.id}/services`, {
      service_id: field(form, "service_id"), sessions_count: Number(field(form, "sessions_count")),
    }), "Service added.", "The service could not be added.").then((ok) => { if (ok) { void refreshManage(manage.id); void load(); } });
  }

  function removeService(serviceId: string) {
    if (!manage) return;
    void run(() => del(`/api/v1/packages/${manage.id}/services/${serviceId}`), "Service removed.", "The service could not be removed.")
      .then((ok) => { if (ok) { void refreshManage(manage.id); void load(); } });
  }

  function handleSell(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!sellPkg) return;
    const form = new FormData(event.currentTarget);
    const patientId = field(form, "patient_id");
    const body: Record<string, unknown> = { patient_id: patientId, idempotency_key: sellKey };
    if (sellMode === "create") {
      body.create_invoice = true;
      if (collectNow) {
        const amount = Number(field(form, "amount") || sellPkg.total_price_minor / 100);
        body.payment = { amount_minor: Math.round(amount * 100), method: field(form, "method") || "cash" };
      }
    } else if (sellMode === "link") {
      const inv = field(form, "invoice_id");
      if (inv) body.invoice_id = inv;
    }
    void run(() => post(`/api/v1/packages/${sellPkg.id}/purchase`, body), "Package sold to patient.", "The purchase could not be completed.").then((ok) => {
      if (ok) { setSellPkg(null); setPatientLookup(patientId); void refreshPatient(patientId); void load(); }
    });
  }

  async function openPurchase(id: string) {
    try { setPurchase(await api<PurchaseDetail>(`/api/v1/packages/patient-purchases/${id}`)); }
    catch (reason) { toast.error(errorMessage(reason, "The purchase could not be loaded.")); }
  }

  function handleConsume(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!purchase) return;
    const form = new FormData(event.currentTarget);
    const reason = field(form, "override_reason");
    void run(() => post(`/api/v1/packages/patient-purchases/${purchase.id}/consume`, {
      service_id: field(form, "service_id") || null,
      override_reason: reason || null,
    }), "Session recorded.", "The session could not be recorded.").then((ok) => {
      if (ok) { void openPurchase(purchase.id); if (patientLookup) void refreshPatient(patientLookup); void load(); }
    });
  }

  const priceLabel = `Price (${clinicCurrency})`;
  const kpis = overview && [
    { label: "ACTIVE PACKAGES", value: overview.active_definitions, note: `${overview.inactive_definitions} inactive` },
    { label: "PACKAGES SOLD", value: overview.total_sold, note: `${overview.active_patient_packages} active` },
    { label: "SESSIONS", value: `${overview.sessions_used}/${overview.sessions_purchased}`, note: `${overview.sessions_remaining} remaining` },
    { label: "EXPIRING · 30D", value: overview.expiring_30d, note: "active packages" },
  ];

  return <main className="workspace-page packages-page">
    <div className="workspace-page-header">
      <div>
        <p className="eyebrow">BUSINESS · SESSION-BASED CARE</p>
        <h1>Packages that <em>keep patients coming back.</em></h1>
        <p className="workspace-page-intro">Bundle services into packages, sell them to patients, and track every session with an auditable ledger.</p>
      </div>
      <div className="header-actions">
        <button className="button button-secondary" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button>
        {can("package.manage") && <button className="button button-primary" onClick={() => setCreateDrawer(true)}>New package <span>＋</span></button>}
      </div>
    </div>

    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" onClick={() => void load()}>Try again <span>→</span></button></div>}

    {kpis && <div className="report-health-grid packages-kpis">
      {kpis.map((k) => <div key={k.label}><strong>{k.value}</strong><span>{k.label}</span><small className="muted-mono">{k.note}</small></div>)}
    </div>}

    <section className="surface-card">
      <div className="surface-card-heading">
        <div><p className="eyebrow">PACKAGE CATALOG</p><h2>Defined packages</h2></div>
        <span className="muted-mono">{packages.length} SHOWN</span>
      </div>
      <div className="invoice-list">
        {!loading && packages.length === 0 && <div className="dashboard-empty"><strong>No packages yet</strong><span>Use “New package” above to bundle services and track sessions.</span></div>}
        {packages.map((pkg) => <article className="invoice-row" key={pkg.id}>
          <div className="invoice-mark">{pkg.name.slice(0, 2).toUpperCase()}</div>
          <div className="invoice-main">
            <h3>{pkg.name}</h3>
            <p>
              {money(pkg.total_price_minor, pkg.currency)}
              {pkg.original_value_minor != null && pkg.original_value_minor > pkg.total_price_minor && <>
                <span className="packages-strike">{money(pkg.original_value_minor, pkg.currency)}</span>
                <span className="packages-save">save {money(pkg.original_value_minor - pkg.total_price_minor, pkg.currency)}</span>
              </>}
              {" · "}{pkg.validity_days} days · {pkg.total_sessions} sessions
            </p>
            {pkg.description && <small className="muted-mono">{pkg.description}</small>}
          </div>
          <div className="invoice-actions">
            <span className={`pipeline-status status-${pkg.status === "active" ? "paid" : pkg.status === "inactive" ? "pending" : "void"}`}>{pkg.status}</span>
            {can("package.manage") && <button className="text-control" disabled={busy} onClick={() => void refreshManage(pkg.id)}>Manage</button>}
            {can("package.manage") && pkg.status === "active" && <button className="button button-secondary" disabled={busy} onClick={() => { setSellKey(crypto.randomUUID()); setSellMode("none"); setCollectNow(false); setSellPkg(pkg); }}>Sell</button>}
          </div>
        </article>)}
      </div>
    </section>

    <section className="surface-card" style={{ marginTop: 20 }}>
      <div className="surface-card-heading">
        <div><p className="eyebrow">PATIENT PACKAGES</p><h2>Purchases &amp; session tracking</h2></div>
        <select className="admin-search-input" value={patientLookup} onChange={(e) => { setPatientLookup(e.target.value); if (e.target.value) void refreshPatient(e.target.value); else setPatientPackages([]); }}>
          <option value="">Choose patient…</option>
          {patients.map((p) => <option key={p.id} value={p.id}>{p.full_name} ({p.patient_number})</option>)}
        </select>
      </div>
      {patientLookup && <div className="invoice-list">
        {patientPackages.length === 0 && <div className="dashboard-empty"><strong>No packages</strong><span>This patient has no purchased packages.</span></div>}
        {patientPackages.map((pp) => {
          const pct = pp.total_sessions > 0 ? Math.round((pp.used_sessions / pp.total_sessions) * 100) : 0;
          return <article className="invoice-row" key={pp.id} style={{ cursor: "pointer" }} onClick={() => void openPurchase(pp.id)}>
            <div className="invoice-mark">{pp.name.slice(0, 2).toUpperCase()}</div>
            <div className="invoice-main">
              <h3>{pp.name}</h3>
              <p>{pp.used_sessions}/{pp.total_sessions} sessions used · {pp.remaining_sessions} remaining</p>
              <div className="packages-progress"><div style={{ width: `${pct}%` }} data-full={pct >= 100} /></div>
              <small className="muted-mono">Purchased {new Date(pp.purchased_at).toLocaleDateString()} · Expires {new Date(pp.expires_at).toLocaleDateString()}</small>
            </div>
            <div className="invoice-actions">
              <span className={`pipeline-status status-${pp.status === "active" ? "paid" : pp.status === "exhausted" ? "pending" : "void"}`}>{pp.status}</span>
            </div>
          </article>;
        })}
      </div>}
    </section>

    {/* Create */}
    <Drawer open={createDrawer} onClose={() => setCreateDrawer(false)} title="New package" subtitle="PACKAGE CATALOG"
      footer={<>
        <button className="button button-secondary" type="button" onClick={() => setCreateDrawer(false)} disabled={busy}>Cancel</button>
        <button className="button button-primary" type="submit" form="create-package-form" disabled={busy}>{busy ? "Saving…" : "Create package"} <span>↗</span></button>
      </>}>
      <form id="create-package-form" className="manage-form packages-form" onSubmit={handleCreate}>
        <label>Name <span className="packages-req">required</span><input name="name" required maxLength={160} placeholder="Hair Transplant · 3 sessions" /></label>
        <label>Description <span className="field-optional">optional</span><textarea name="description" maxLength={2000} rows={3} placeholder="What this package includes, terms, etc." /></label>
        <div className="packages-grid-2">
          <label>{priceLabel} <span className="packages-req">required</span><input name="price" type="number" min={0} step="0.01" required placeholder="0.00" /></label>
          <label>Original value <span className="field-optional">optional</span><input name="original_price" type="number" min={0} step="0.01" placeholder="0.00" /></label>
        </div>
        <label>Validity (days) <span className="packages-req">required</span><input name="validity_days" type="number" min={1} max={3650} required defaultValue={365} /></label>
        <p className="muted-mono packages-form-hint">Original value shows patients their savings — leave blank if there is none.</p>
      </form>
    </Drawer>

    {/* Manage */}
    <Drawer open={!!manage} onClose={() => setManage(null)} title={manage?.name ?? ""} subtitle={manage ? `${manage.status} · v${manage.version}` : undefined} width={540}>
      {manage && <div className="packages-manage">
        <form className="manage-form packages-form" onSubmit={handleEdit}>
          <label>Name<input name="name" required maxLength={160} defaultValue={manage.name} /></label>
          <label>Description <span className="field-optional">optional</span><textarea name="description" maxLength={2000} rows={2} defaultValue={manage.description ?? ""} /></label>
          <div className="packages-grid-2">
            <label>{priceLabel}<input name="price" type="number" min={0} step="0.01" required defaultValue={(manage.total_price_minor / 100).toFixed(2)} /></label>
            <label>Original value <span className="field-optional">optional</span><input name="original_price" type="number" min={0} step="0.01" defaultValue={manage.original_value_minor != null ? (manage.original_value_minor / 100).toFixed(2) : ""} /></label>
          </div>
          <label>Validity (days)<input name="validity_days" type="number" min={1} max={3650} required defaultValue={manage.validity_days} /></label>
          <div className="form-actions"><button className="button button-primary" type="submit" disabled={busy}>Save changes<span>↗</span></button></div>
        </form>

        <div className="packages-status-actions">
          {manage.status !== "active" && manage.status !== "archived" && <button className="button button-secondary" disabled={busy} onClick={() => changeStatus("activate")}>Activate</button>}
          {manage.status === "active" && <button className="button button-secondary" disabled={busy} onClick={() => changeStatus("deactivate")}>Deactivate</button>}
          {manage.status === "archived" ? <button className="button button-secondary" disabled={busy} onClick={() => changeStatus("unarchive")}>Unarchive</button>
            : <button className="button button-danger" disabled={busy} onClick={() => void confirmArchive()}>Archive</button>}
          <span className="muted-mono">{manage.sold.total_sold} sold · {manage.sold.active_count} active</span>
        </div>

        <h3 className="eyebrow packages-sub">INCLUDED SERVICES · {manage.total_sessions} sessions</h3>
        <div className="invoice-list">
          {manage.services.length === 0 && <div className="dashboard-empty"><strong>No services</strong><span>Add at least one service before selling.</span></div>}
          {manage.services.map((s) => <article className="invoice-row" key={s.service_id}>
            <div className="invoice-main"><h3>{s.name}</h3><p>{s.sessions_count} session{s.sessions_count === 1 ? "" : "s"}</p></div>
            <div className="invoice-actions"><button className="text-control" disabled={busy} onClick={() => removeService(s.service_id)}>Remove</button></div>
          </article>)}
        </div>
        <form className="manage-form packages-form" onSubmit={handleAddService}>
          <div className="packages-grid-2">
            <label>Add service<select name="service_id" required><option value="">Choose…</option>{services.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
            <label>Sessions<input name="sessions_count" type="number" min={1} max={1000} required defaultValue={1} /></label>
          </div>
          <div className="form-actions"><button className="button button-secondary" type="submit" disabled={busy}>Add service</button></div>
        </form>
      </div>}
    </Drawer>

    {/* Sell */}
    <Drawer open={!!sellPkg} onClose={() => setSellPkg(null)} title="Sell package" subtitle={sellPkg?.name} width={520}>
      {sellPkg && <form className="manage-form packages-form" onSubmit={handleSell}>
        <p className="packages-sell-summary">{money(sellPkg.total_price_minor, sellPkg.currency)} · {sellPkg.total_sessions} sessions · valid {sellPkg.validity_days} days</p>
        <label>Patient<select name="patient_id" required><option value="">Choose patient…</option>{patients.map((p) => <option key={p.id} value={p.id}>{p.full_name} ({p.patient_number})</option>)}</select></label>
        <label>Billing<select value={sellMode} onChange={(e) => setSellMode(e.target.value as "none" | "create" | "link")}>
          <option value="none">No invoice — record entitlement only</option>
          <option value="create">Create an invoice for this sale</option>
          <option value="link">Link an existing invoice</option>
        </select></label>
        {sellMode === "create" && <>
          <label className="packages-check"><input type="checkbox" checked={collectNow} onChange={(e) => setCollectNow(e.target.checked)} /> Collect payment now</label>
          {collectNow ? <div className="packages-grid-2">
            <label>Amount ({sellPkg.currency})<input name="amount" type="number" min={0} step="0.01" defaultValue={(sellPkg.total_price_minor / 100).toFixed(2)} /></label>
            <label>Method<select name="method" defaultValue="cash"><option value="cash">Cash</option><option value="card">Card</option><option value="bank_transfer">Bank transfer</option><option value="online">Online</option><option value="other">Other</option></select></label>
          </div> : <p className="muted-mono">The invoice is created as <strong>unpaid</strong> — collect payment later in Billing. Unpaid invoices are never counted as collected.</p>}
        </>}
        {sellMode === "link" && <label>Existing invoice ID<input name="invoice_id" placeholder="Invoice UUID for this patient" /></label>}
        <div className="form-actions"><button className="button button-primary" type="submit" disabled={busy}>{busy ? "Processing…" : "Confirm sale"}<span>↗</span></button></div>
      </form>}
    </Drawer>

    {/* Purchase detail + consume */}
    <Drawer open={!!purchase} onClose={() => setPurchase(null)} title={purchase?.name ?? ""} subtitle={purchase ? `${purchase.used_sessions}/${purchase.total_sessions} used · ${purchase.remaining_sessions} left` : undefined} width={520}>
      {purchase && <div className="packages-manage">
        <span className={`pipeline-status status-${purchase.status === "active" ? "paid" : purchase.status === "exhausted" ? "pending" : "void"}`}>{purchase.status}</span>
        {can("package.manage") && purchase.status === "active" && <form className="manage-form packages-form" onSubmit={handleConsume}>
          <label>Use a session for<select name="service_id"><option value="">Any included service</option>{purchase.sessions.filter((s) => s.status === "planned" && s.service_id).map((s) => s.service_id).filter((v, i, a) => a.indexOf(v) === i).map((sid) => { const row = purchase.sessions.find((s) => s.service_id === sid); return <option key={sid} value={sid ?? ""}>{row?.service_name ?? sid}</option>; })}</select></label>
          <label>Override reason <span className="field-optional">only if no planned session remains</span><input name="override_reason" maxLength={500} placeholder="Authorized overuse reason" /></label>
          <div className="form-actions"><button className="button button-primary" type="submit" disabled={busy}>Record session<span>↗</span></button></div>
        </form>}
        <h3 className="eyebrow packages-sub">SESSION HISTORY</h3>
        <div className="invoice-list">
          {purchase.sessions.map((s) => <article className="invoice-row" key={s.id}>
            <div className="invoice-main">
              <h3>{s.service_name ?? "Any service"}</h3>
              <p>{s.status}{s.used_at ? ` · ${new Date(s.used_at).toLocaleString()}` : ""}</p>
              {s.override_reason && <small className="muted-mono">Override: {s.override_reason}</small>}
            </div>
            <div className="invoice-actions"><span className={`pipeline-status status-${s.status === "used" ? "paid" : s.status === "planned" ? "pending" : "contacted"}`}>{s.status}</span></div>
          </article>)}
        </div>
      </div>}
    </Drawer>
  </main>;
}

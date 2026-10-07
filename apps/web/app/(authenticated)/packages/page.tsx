"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, errorMessage, label, money, post } from "../_lib/client";
import Drawer from "../_lib/drawer";
import { useToast } from "../_lib/toast";
import { useConfirm } from "../_lib/confirm";

type Session = { permissions?: string[] };
type Package = { id: string; name: string; description: string | null; specialty_id: string | null; total_price_minor: number; original_value_minor: number | null; currency: string; validity_days: number; status: string; version: number; created_at: string; total_sessions: number };
type Service = { id: string; name: string; category: string | null; duration_minutes: number; amount_minor: number | null; currency: string | null };
type Patient = { id: string; full_name: string; patient_number: string };
type PatientPackage = { id: string; patient_id: string; package_definition_id: string; name: string; purchased_at: string; expires_at: string; status: string; total_sessions: number; used_sessions: number; remaining_sessions: number; version: number };

export default function PackagesPage() {
  const [permissions, setPermissions] = useState<string[]>([]);
  const [packages, setPackages] = useState<Package[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [createDrawer, setCreateDrawer] = useState(false);
  const [serviceDrawer, setServiceDrawer] = useState<string | null>(null);
  const [sellDrawer, setSellDrawer] = useState<string | null>(null);
  const [patientLookup, setPatientLookup] = useState<string | null>(null);
  const [patientPackages, setPatientPackages] = useState<PatientPackage[]>([]);
  const [expandedPkg, setExpandedPkg] = useState<string | null>(null);

  const toast = useToast();
  const confirm = useConfirm();
  const can = useCallback((p: string) => permissions.includes(p), [permissions]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [session, pkgRows, svcRows, patRows] = await Promise.all([
        api<Session>("/api/v1/auth/me"),
        api<Package[]>("/api/v1/packages"),
        api<Service[]>("/api/v1/services?limit=100"),
        api<Patient[]>("/api/v1/patients?limit=50").catch(() => []),
      ]);
      setPermissions(session.permissions ?? []);
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

  // ── Create package ──
  function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const price = Math.round(Number(field(form, "price")) * 100);
    const original = field(form, "original_price") ? Math.round(Number(field(form, "original_price")) * 100) : null;
    void run(
      () => post("/api/v1/packages", {
        name: field(form, "name"),
        description: field(form, "description") || null,
        total_price_minor: price,
        original_value_minor: original,
        currency: "PKR",
        validity_days: Number(field(form, "validity_days")),
      }),
      "Package created.", "The package could not be created."
    ).then(() => setCreateDrawer(false));
  }

  // ── Add service to package ──
  function handleAddService(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!serviceDrawer) return;
    const form = new FormData(event.currentTarget);
    void run(
      () => post(`/api/v1/packages/${serviceDrawer}/services`, {
        service_id: field(form, "service_id"),
        sessions_count: Number(field(form, "sessions_count")),
      }),
      "Service added to package.", "The service could not be added."
    ).then(() => setServiceDrawer(null));
  }

  // ── Sell package to patient ──
  function handleSell(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!sellDrawer) return;
    const form = new FormData(event.currentTarget);
    void run(
      () => post(`/api/v1/packages/${sellDrawer}/purchase`, {
        patient_id: field(form, "patient_id"),
      }),
      "Package sold to patient.", "The purchase could not be completed."
    ).then(() => setSellDrawer(null));
  }

  // ── Load patient packages ──
  async function lookupPatientPackages(patientId: string) {
    setPatientLookup(patientId);
    try {
      const rows = await api<PatientPackage[]>(`/api/v1/packages/patients/${patientId}`);
      setPatientPackages(rows ?? []);
    } catch (reason) {
      toast.error(errorMessage(reason, "Patient packages could not be loaded."));
      setPatientPackages([]);
    }
  }

  // ── Consume session ──
  async function consumeSession(purchaseId: string) {
    const ok = await confirm({ message: "Mark one session as used?" });
    if (!ok) return;
    void run(
      () => post(`/api/v1/packages/patient-purchases/${purchaseId}/consume`, {}),
      "Session consumed.", "The session could not be consumed."
    ).then(() => { if (patientLookup) void lookupPatientPackages(patientLookup); });
  }

  const activePackages = useMemo(() => packages.filter((p) => p.status === "active"), [packages]);

  return <main className="workspace-page packages-page">
    <div className="workspace-page-header">
      <div>
        <p className="eyebrow">BUSINESS · SESSION-BASED CARE</p>
        <h1>Packages that <em>keep patients coming back.</em></h1>
        <p className="workspace-page-intro">Bundle services into packages with session tracking. Sell to patients and track usage across appointments.</p>
      </div>
      <div className="header-actions">
        <button className="button button-secondary" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button>
        {can("package.manage") && <button className="button button-primary" onClick={() => setCreateDrawer(true)}>New package <span>＋</span></button>}
      </div>
    </div>

    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" onClick={() => void load()}>Try again <span>→</span></button></div>}

    {/* ═══ PACKAGE CATALOG ═══ */}
    <section className="surface-card">
      <div className="surface-card-heading">
        <div><p className="eyebrow">PACKAGE CATALOG</p><h2>Defined packages</h2></div>
        <span className="muted-mono">{activePackages.length} ACTIVE</span>
      </div>

      <div className="invoice-list">
        {!loading && packages.length === 0 && <div className="dashboard-empty"><strong>No packages yet</strong><span>Create a package to bundle services and track sessions.</span></div>}
        {packages.map((pkg) => <article className="invoice-row" key={pkg.id} style={{ cursor: "pointer" }} onClick={() => setExpandedPkg(expandedPkg === pkg.id ? null : pkg.id)}>
          <div className="invoice-mark">{pkg.name.slice(0, 2).toUpperCase()}</div>
          <div className="invoice-main">
            <h3>{pkg.name}</h3>
            <p>
              {money(pkg.total_price_minor, pkg.currency)}
              {pkg.original_value_minor != null && pkg.original_value_minor > pkg.total_price_minor && <span style={{ textDecoration: "line-through", color: "var(--text-muted, #6b7280)", marginLeft: 6, fontSize: "0.8rem" }}>{money(pkg.original_value_minor, pkg.currency)}</span>}
              {" · "}{pkg.validity_days} days · {pkg.total_sessions} sessions
            </p>
            {pkg.description && <small style={{ color: "var(--text-muted, #6b7280)" }}>{pkg.description}</small>}
            {expandedPkg === pkg.id && <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px dashed var(--border-subtle, #e5e5e3)", display: "flex", gap: 8, flexWrap: "wrap" }}>
              {can("package.manage") && <button className="button button-secondary" disabled={busy} onClick={(e) => { e.stopPropagation(); setServiceDrawer(pkg.id); }}>Add service</button>}
              {can("package.manage") && <button className="button button-primary" disabled={busy} onClick={(e) => { e.stopPropagation(); setSellDrawer(pkg.id); }}>Sell to patient</button>}
            </div>}
          </div>
          <div className="invoice-actions">
            <span className={`pipeline-status status-${pkg.status === "active" ? "paid" : "void"}`}>{pkg.status}</span>
          </div>
        </article>)}
      </div>
    </section>

    {/* ═══ PATIENT PACKAGES ═══ */}
    <section className="surface-card" style={{ marginTop: 20 }}>
      <div className="surface-card-heading">
        <div><p className="eyebrow">PATIENT PACKAGES</p><h2>Active purchases &amp; session tracking</h2></div>
      </div>

      <div style={{ padding: "12px 0" }}>
        <label style={{ fontSize: "0.85rem" }}>
          Select patient to view packages
          <select style={{ marginLeft: 8, padding: "4px 8px", borderRadius: 4, border: "1px solid var(--border-subtle, #e5e5e3)", fontSize: "0.85rem" }} value={patientLookup ?? ""} onChange={(e) => { if (e.target.value) void lookupPatientPackages(e.target.value); else { setPatientLookup(null); setPatientPackages([]); } }}>
            <option value="">Choose patient…</option>
            {patients.map((p) => <option key={p.id} value={p.id}>{p.full_name} ({p.patient_number})</option>)}
          </select>
        </label>
      </div>

      {patientLookup && <div className="invoice-list">
        {patientPackages.length === 0 && <div className="dashboard-empty"><strong>No packages</strong><span>This patient has no purchased packages.</span></div>}
        {patientPackages.map((pp) => {
          const pct = pp.total_sessions > 0 ? Math.round((pp.used_sessions / pp.total_sessions) * 100) : 0;
          const expired = pp.status === "expired" || new Date(pp.expires_at) < new Date();
          return <article className="invoice-row" key={pp.id}>
            <div className="invoice-mark" style={{ background: expired ? "var(--red-bg, #fef2f2)" : undefined }}>{pp.name.slice(0, 2).toUpperCase()}</div>
            <div className="invoice-main">
              <h3>{pp.name}</h3>
              <p>{pp.used_sessions}/{pp.total_sessions} sessions used · {pp.remaining_sessions} remaining</p>
              <div style={{ height: 6, background: "var(--border-subtle, #e5e5e3)", borderRadius: 3, overflow: "hidden", marginTop: 4, maxWidth: 240 }}>
                <div style={{ height: "100%", width: `${pct}%`, background: pct >= 100 ? "var(--red, #b91c1c)" : pct > 70 ? "var(--amber, #92400e)" : "var(--accent, #274c42)", borderRadius: 3, transition: "width 0.3s" }} />
              </div>
              <small style={{ color: "var(--text-muted, #6b7280)" }}>
                Purchased {new Date(pp.purchased_at).toLocaleDateString()} · Expires {new Date(pp.expires_at).toLocaleDateString()}
              </small>
            </div>
            <div className="invoice-actions">
              <span className={`pipeline-status status-${pp.status === "active" ? "paid" : pp.status === "exhausted" ? "contacted" : "void"}`}>{pp.status}</span>
              {can("package.manage") && pp.status === "active" && !expired && pp.remaining_sessions > 0 && (
                <button className="button button-secondary" disabled={busy} onClick={() => void consumeSession(pp.id)}>Use session</button>
              )}
            </div>
          </article>;
        })}
      </div>}
    </section>

    {/* ═══ CREATE PACKAGE DRAWER ═══ */}
    <Drawer open={createDrawer} onClose={() => setCreateDrawer(false)} title="New package">
      <form className="manage-form" onSubmit={handleCreate} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <label>Name<input name="name" required maxLength={160} placeholder="Hair Transplant 3-Session" /></label>
        <label>Description <span className="field-optional">optional</span><textarea name="description" maxLength={2000} rows={2} placeholder="What this package includes" style={{ width: "100%" }} /></label>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <label>Package price (PKR)<input name="price" type="number" min={0} step="0.01" required placeholder="25000" /></label>
          <label>Original value <span className="field-optional">optional</span><input name="original_price" type="number" min={0} step="0.01" placeholder="30000" /></label>
        </div>
        <label>Validity (days)<input name="validity_days" type="number" min={1} max={3650} required defaultValue={365} /></label>
        <div className="form-actions"><button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Create package"}<span>↗</span></button></div>
      </form>
    </Drawer>

    {/* ═══ ADD SERVICE DRAWER ═══ */}
    <Drawer open={!!serviceDrawer} onClose={() => setServiceDrawer(null)} title="Add service to package">
      <form className="manage-form" onSubmit={handleAddService} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <label>Service
          <select name="service_id" required>
            <option value="">Choose service…</option>
            {services.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.duration_minutes} min{s.amount_minor != null ? ` · ${money(s.amount_minor, s.currency ?? "PKR")}` : ""})</option>)}
          </select>
        </label>
        <label>Sessions included<input name="sessions_count" type="number" min={1} max={1000} required defaultValue={1} /></label>
        <div className="form-actions"><button className="button button-primary" type="submit" disabled={busy}>{busy ? "Adding…" : "Add service"}<span>↗</span></button></div>
      </form>
    </Drawer>

    {/* ═══ SELL DRAWER ═══ */}
    <Drawer open={!!sellDrawer} onClose={() => setSellDrawer(null)} title="Sell package to patient">
      <form className="manage-form" onSubmit={handleSell} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <label>Patient
          <select name="patient_id" required>
            <option value="">Choose patient…</option>
            {patients.map((p) => <option key={p.id} value={p.id}>{p.full_name} ({p.patient_number})</option>)}
          </select>
        </label>
        <div className="form-actions"><button className="button button-primary" type="submit" disabled={busy}>{busy ? "Processing…" : "Sell package"}<span>↗</span></button></div>
      </form>
    </Drawer>
  </main>;
}

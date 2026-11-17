"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, errorMessage } from "../_lib/client";
import { useToast } from "../_lib/toast";
import { useClinicCurrency } from "../_lib/clinic-context";

type Pair = { current: number; prior: number };
type Kpis = { appointments: Pair; appointments_completed: Pair; no_shows: Pair; new_patients: Pair; leads: Pair; conversions: Pair; paid_minor?: Pair; invoiced_minor?: Pair; patients_billed?: Pair };
type Report = { period_days: number; appointments: { status: string; count: number }[]; patients_created: number; leads: { status: string; count: number }[]; kpis: Kpis; financial: { invoices: number; invoiced_minor: number; outstanding_minor: number; outstanding_all_minor: number; paid_minor: number; payment_methods: { method: string; payments: number; paid_minor: number }[]; aging: { bucket: string; invoices: number; outstanding_minor: number }[] } | null; package_utilization: { packages: number; sessions_purchased: number; sessions_used: number; sessions_remaining: number }; operational: { waiting_patients: number; followups_due: number; no_shows: number; low_inventory: number } };
type Branch = { id: string; name: string };
type Session = { permissions?: string[] };

const label = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const money = (minor: number, currency: string) => new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(minor / 100);
const rate = (num: number, den: number) => (den > 0 ? num / den : 0);
const pctFmt = (value: number) => `${Math.round(value * 100)}%`;
// Count/amount KPIs compare as a % change; rate KPIs compare in percentage points.
const delta = (current: number, prior: number): { label: string; up: boolean } => {
  if (prior === 0) return { label: current > 0 ? "new" : "—", up: current >= 0 };
  const change = Math.round(((current - prior) / prior) * 100);
  return { label: `${change >= 0 ? "+" : ""}${change}% vs prior`, up: change >= 0 };
};
const pointDelta = (current: number, prior: number): { label: string; up: boolean } => {
  const points = Math.round((current - prior) * 100);
  return { label: `${points >= 0 ? "+" : ""}${points} pts vs prior`, up: points >= 0 };
};
// Reuse the Analytics card trend colours; for "lower is better" KPIs an increase is a down-trend.
const trendCls = (up: boolean, goodWhenUp = true) => (up === goodWhenUp ? "trend-up" : "trend-down");

export default function ReportsPage() {
  const clinicCurrency = useClinicCurrency();
  const [report, setReport] = useState<Report | null>(null);
  const [days, setDays] = useState("30");
  const [branchId, setBranchId] = useState("");
  const [branches, setBranches] = useState<Branch[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [section, setSection] = useState<"care" | "demand" | "cash" | "ops">("care");
  const toast = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ days });
      if (branchId) params.set("branch_id", branchId);
      const [reportData, sessionData, branchData] = await Promise.all([
        api<Report>(`/api/v1/operations/reporting-summary?${params}`),
        api<Session>("/api/v1/auth/me"),
        api<Branch[]>("/api/v1/branches?limit=100").catch(() => []),
      ]);
      setReport(reportData);
      setPermissions(sessionData.permissions ?? []);
      setBranches(branchData ?? []);
    } catch (reason) {
      setError(errorMessage(reason, "The report could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, [days, branchId]);
  useEffect(() => { void load(); }, [load]);

  // The backend export queue only knows patient-access and audit exports, so the
  // summary is written to CSV from the data already on screen.
  function exportReport() {
    if (!report) return;
    const rows: string[][] = [["section", "key", "count", "amount_minor"]];
    report.appointments.forEach((a) => rows.push(["appointments", a.status, String(a.count), ""]));
    rows.push(["patients", "created", String(report.patients_created), ""]);
    report.leads.forEach((l) => rows.push(["leads", l.status, String(l.count), ""]));
    Object.entries(report.kpis).forEach(([key, pair]) => pair && rows.push(["kpi", key, String(pair.current), String(pair.prior)]));
    if (report.financial) {
      rows.push(["financial", "invoices", String(report.financial.invoices), String(report.financial.invoiced_minor)]);
      rows.push(["financial", "paid", "", String(report.financial.paid_minor)]);
      rows.push(["financial", "outstanding_window", "", String(report.financial.outstanding_minor)]);
      rows.push(["financial", "outstanding_all_open", "", String(report.financial.outstanding_all_minor)]);
      report.financial.payment_methods.forEach((m) => rows.push(["payment_method", m.method, String(m.payments), String(m.paid_minor)]));
      report.financial.aging.forEach((b) => rows.push(["aging", b.bucket, String(b.invoices), String(b.outstanding_minor)]));
    }
    Object.entries(report.package_utilization).forEach(([k, v]) => rows.push(["packages", k, String(v), ""]));
    Object.entries(report.operational).forEach(([k, v]) => rows.push(["operational", k, String(v), ""]));
    const csv = rows.map((r) => r.map((c) => `"${c.replaceAll('"', '""')}"`).join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url; a.download = `report-${report.period_days}d-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast.success("CSV downloaded.");
  }

  const can = (p: string) => permissions.includes(p);
  const appointmentTotal = useMemo(() => report?.appointments.reduce((total, item) => total + item.count, 0) ?? 0, [report]);
  const leadTotal = useMemo(() => report?.leads.reduce((total, item) => total + item.count, 0) ?? 0, [report]);
  const maxAppointment = Math.max(...(report?.appointments.map((item) => item.count) ?? [1]), 1);
  const kpiView = useMemo(() => {
    if (!report) return null;
    const k = report.kpis;
    const fin = k.paid_minor && k.invoiced_minor && k.patients_billed ? { paid: k.paid_minor, invoiced: k.invoiced_minor, billed: k.patients_billed } : null;
    const perPatient = (paid: number, patients: number) => (patients > 0 ? paid / patients : 0);
    return {
      hero: {
        appointments: delta(k.appointments.current, k.appointments.prior),
        newPatients: delta(k.new_patients.current, k.new_patients.prior),
        leads: delta(k.leads.current, k.leads.prior),
      },
      conversion: { value: pctFmt(rate(k.conversions.current, k.leads.current)), d: pointDelta(rate(k.conversions.current, k.leads.current), rate(k.conversions.prior, k.leads.prior)) },
      showUp: { value: pctFmt(rate(k.appointments_completed.current, k.appointments.current)), d: pointDelta(rate(k.appointments_completed.current, k.appointments.current), rate(k.appointments_completed.prior, k.appointments.prior)) },
      noShow: { value: pctFmt(rate(k.no_shows.current, k.appointments.current)), d: pointDelta(rate(k.no_shows.current, k.appointments.current), rate(k.no_shows.prior, k.appointments.prior)) },
      collection: fin ? { value: pctFmt(rate(fin.paid.current, fin.invoiced.current)), d: pointDelta(rate(fin.paid.current, fin.invoiced.current), rate(fin.paid.prior, fin.invoiced.prior)) } : null,
      revPerPatient: fin ? { value: money(Math.round(perPatient(fin.paid.current, fin.billed.current)), clinicCurrency), d: delta(perPatient(fin.paid.current, fin.billed.current), perPatient(fin.paid.prior, fin.billed.prior)) } : null,
    };
  }, [report, clinicCurrency]);
  return <main className="workspace-page reports-page">
    <div className="workspace-page-header">
      <div>
        <p className="eyebrow">BUSINESS</p>
        <h1>See the clinic <em>clearly.</em></h1>
        <p className="workspace-page-intro">Demand, care, cash, and the operational edges that need attention. For day-by-day trends and charts, open <Link className="text-link" href="/analytics">Analytics ↗</Link></p>
      </div>
      <div className="header-actions">
        <label className="report-period">Window
          <select value={days} onChange={(e) => setDays(e.target.value)}>
            <option value="7">Last 7 days</option>
            <option value="30">Last 30 days</option>
            <option value="90">Last 90 days</option>
            <option value="365">Last year</option>
          </select>
        </label>
        {branches.length > 1 && <label className="report-period">Branch
          <select value={branchId} onChange={(e) => setBranchId(e.target.value)}>
            <option value="">All branches</option>
            {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        </label>}
        {can("patient.export") && <button className="button button-secondary" disabled={!report} onClick={exportReport}>Export CSV</button>}
        <button className="button button-secondary" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button>
      </div>
    </div>

    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" onClick={() => void load()}>Try again <span>→</span></button></div>}

    {loading && !report && <div className="dashboard-empty" role="status"><strong>Reading the clinic signal</strong><span>Aggregating only the records in your authorized scope…</span></div>}

    {report && <>
      <div className="report-hero-grid">
        <div className="report-hero-card report-hero-dark"><span className="eyebrow">APPOINTMENTS</span><strong>{appointmentTotal}</strong><p>appointments in the last {report.period_days} days{kpiView && <> · <span className={trendCls(kpiView.hero.appointments.up)}>{kpiView.hero.appointments.label}</span></>}</p></div>
        <div className="report-hero-card"><span className="eyebrow">NEW PATIENTS</span><strong>{report.patients_created}</strong><p>new patient records created{kpiView && <> · <span className={trendCls(kpiView.hero.newPatients.up)}>{kpiView.hero.newPatients.label}</span></>}</p></div>
        <div className="report-hero-card report-hero-warm"><span className="eyebrow">LEADS</span><strong>{leadTotal}</strong><p>enquiries entering the pipeline{kpiView && <> · <span className={trendCls(kpiView.hero.leads.up)}>{kpiView.hero.leads.label}</span></>}</p></div>
      </div>

      {kpiView && <div className="analytics-grid report-kpi-grid">
        <div className="analytics-card"><p className="eyebrow">LEAD → PATIENT</p><strong>{kpiView.conversion.value}</strong><small className={trendCls(kpiView.conversion.d.up)}>{kpiView.conversion.d.label}</small></div>
        <div className="analytics-card"><p className="eyebrow">SHOW-UP RATE</p><strong>{kpiView.showUp.value}</strong><small className={trendCls(kpiView.showUp.d.up)}>{kpiView.showUp.d.label}</small></div>
        <div className="analytics-card"><p className="eyebrow">NO-SHOW RATE</p><strong>{kpiView.noShow.value}</strong><small className={trendCls(kpiView.noShow.d.up, false)}>{kpiView.noShow.d.label}</small></div>
        {kpiView.collection && <div className="analytics-card"><p className="eyebrow">COLLECTION RATE</p><strong>{kpiView.collection.value}</strong><small className={trendCls(kpiView.collection.d.up)}>{kpiView.collection.d.label}</small></div>}
        {kpiView.revPerPatient && <div className="analytics-card"><p className="eyebrow">REVENUE / PATIENT</p><strong>{kpiView.revPerPatient.value}</strong><small className={trendCls(kpiView.revPerPatient.d.up)}>{kpiView.revPerPatient.d.label}</small></div>}
      </div>}

      {branchId && <p className="report-branch-note">New patients, cash position, packages, waiting patients and follow-ups are clinic-wide — those records carry no branch, so the branch filter does not change them.</p>}

      <div className="pipeline-toolbar"><div className="pipeline-tabs" role="tablist" aria-label="Report sections">
        <button role="tab" aria-selected={section === "care"} className={section === "care" ? "active" : ""} onClick={() => setSection("care")}>Care Flow</button>
        <button role="tab" aria-selected={section === "demand"} className={section === "demand" ? "active" : ""} onClick={() => setSection("demand")}>Demand</button>
        <button role="tab" aria-selected={section === "cash"} className={section === "cash" ? "active" : ""} onClick={() => setSection("cash")}>Cash Position</button>
        <button role="tab" aria-selected={section === "ops"} className={section === "ops" ? "active" : ""} onClick={() => setSection("ops")}>Operational Health</button>
      </div></div>

      {section === "care" && <section className="surface-card report-card">
        <div className="surface-card-heading"><div><p className="eyebrow">CARE FLOW</p><h2>Appointments by state</h2></div><span className="muted-mono">{report.period_days} DAYS</span></div>
        <div className="report-bars">
          {report.appointments.length === 0 && <div className="dashboard-empty"><strong>No appointment activity</strong><span>There is no activity in this reporting window.</span></div>}
          {report.appointments.map((item) => <div className="report-bar-row" key={item.status}><span>{label(item.status)}</span><div><i style={{ width: `${Math.max((item.count / maxAppointment) * 100, item.count ? 4 : 0)}%` }} /></div><b>{item.count}</b></div>)}
        </div>
        <div className="report-card-links"><Link className="text-link" href="/schedule">Open Schedule <span>↗</span></Link></div>
      </section>}

      {section === "demand" && <section className="surface-card report-card">
        <div className="surface-card-heading"><div><p className="eyebrow">DEMAND</p><h2>Lead pipeline</h2></div><span className="muted-mono">{leadTotal} TOTAL</span></div>
        <div className="report-list">
          {report.leads.length === 0 && <div className="dashboard-empty"><strong>No lead activity</strong><span>New enquiries will appear here as they arrive.</span></div>}
          {report.leads.map((item) => <div className="report-list-row" key={item.status}><span className={`pipeline-status status-${item.status}`}>{label(item.status)}</span><strong>{item.count}</strong></div>)}
        </div>
        <div className="report-card-links"><Link className="text-link" href="/queue">Open Queue <span>↗</span></Link></div>
      </section>}

      {section === "cash" && <section className="surface-card report-card">
        <div className="surface-card-heading"><div><p className="eyebrow">CASH POSITION</p><h2>Collected and open</h2></div><span className="muted-mono">AUTHORIZED VIEW</span></div>
        {report.financial ? <div className="report-finance">
          <div><span>Collected · this period</span><strong>{money(report.financial.paid_minor, clinicCurrency)}</strong></div>
          <div><span>Outstanding · all open</span><strong>{money(report.financial.outstanding_all_minor, clinicCurrency)}</strong></div>
          <small>{report.financial.invoices} invoices issued in this window; outstanding and the aging buckets below cover every open invoice.</small>
          <div className="report-mini-list"><strong>Payment methods</strong>{report.financial.payment_methods.map((item) => <span key={item.method}>{label(item.method)} · {money(item.paid_minor, clinicCurrency)}</span>)}</div>
          <div className="report-mini-list"><strong>Outstanding aging</strong>{report.financial.aging.map((item) => <span key={item.bucket}>{label(item.bucket)} · {money(item.outstanding_minor, clinicCurrency)}</span>)}</div>
        </div> : <div className="dashboard-empty"><strong>Financial data restricted</strong><span>Your role does not include billing.read.</span></div>}
        <div className="report-card-links"><Link className="text-link" href="/billing">Open Billing <span>↗</span></Link><Link className="text-link" href="/finance">Open Finance <span>↗</span></Link></div>
      </section>}

      {section === "ops" && <section className="surface-card report-card">
        <div className="surface-card-heading"><div><p className="eyebrow">OPERATIONAL HEALTH</p><h2>Where attention is due</h2></div></div>
        <div className="report-health-grid">
          <div><strong>{report.operational.waiting_patients}</strong><span>waiting patients</span></div>
          <div><strong>{report.operational.followups_due}</strong><span>follow-ups due</span></div>
          <div><strong>{report.operational.no_shows}</strong><span>no-shows</span></div>
          <div><strong>{report.operational.low_inventory}</strong><span>low-stock items</span></div>
        </div>
        <div className="report-card-links"><Link className="text-link" href="/operations">Follow-ups <span>↗</span></Link><Link className="text-link" href="/leads">Leads <span>↗</span></Link><Link className="text-link" href="/inventory">Inventory <span>↗</span></Link></div>
      </section>}

      <section className="surface-card report-card report-package-card">
        <div className="surface-card-heading"><div><p className="eyebrow">TREATMENT PACKAGES</p><h2>Sessions in motion</h2></div><span className="muted-mono">{report.package_utilization.packages} PACKAGES</span></div>
        <div className="report-health-grid">
          <div><strong>{report.package_utilization.sessions_purchased}</strong><span>sessions purchased</span></div>
          <div><strong>{report.package_utilization.sessions_used}</strong><span>sessions used</span></div>
          <div><strong>{report.package_utilization.sessions_remaining}</strong><span>sessions remaining</span></div>
        </div>
      </section>
    </>}
  </main>;
}

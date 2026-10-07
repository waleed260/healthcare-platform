"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import anime from "animejs";
import { api, errorMessage, post } from "../_lib/client";
import { useToast } from "../_lib/toast";

type Report = { period_days: number; appointments: { status: string; count: number }[]; patients_created: number; leads: { status: string; count: number }[]; financial: { invoices: number; invoiced_minor: number; outstanding_minor: number; paid_minor: number; payment_methods: { method: string; payments: number; paid_minor: number }[]; aging: { bucket: string; invoices: number; outstanding_minor: number }[] } | null; package_utilization: { packages: number; sessions_purchased: number; sessions_used: number; sessions_remaining: number }; operational: { waiting_patients: number; followups_due: number; no_shows: number; low_inventory: number } };
type Branch = { id: string; name: string };
type Session = { permissions?: string[] };

const label = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const money = (minor: number, currency = "PKR") => new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(minor / 100);

export default function ReportsPage() {
  const [report, setReport] = useState<Report | null>(null);
  const [days, setDays] = useState("30");
  const [branchId, setBranchId] = useState("");
  const [branches, setBranches] = useState<Branch[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
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

  async function exportReport(format: string) {
    setExporting(true);
    try {
      await post("/api/v1/governance/exports", { export_type: "reporting_summary", format });
      toast.success(`${format.toUpperCase()} export queued. Check the exports list for download.`);
    } catch (reason) {
      toast.error(errorMessage(reason, "The export could not be started."));
    } finally {
      setExporting(false);
    }
  }

  const can = (p: string) => permissions.includes(p);
  const appointmentTotal = useMemo(() => report?.appointments.reduce((total, item) => total + item.count, 0) ?? 0, [report]);
  const leadTotal = useMemo(() => report?.leads.reduce((total, item) => total + item.count, 0) ?? 0, [report]);
  const maxAppointment = Math.max(...(report?.appointments.map((item) => item.count) ?? [1]), 1);

  const rptRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (loading || !rptRef.current) return;
    anime({ targets: rptRef.current.querySelectorAll(".surface-card, .analytics-card, .inventory-summary > div"), opacity: [0, 1], translateY: [22, 0], duration: 500, delay: anime.stagger(50, { start: 120 }), easing: "easeOutCubic" });
  }, [loading]);

  return <main className="workspace-page reports-page" ref={rptRef}>
    <div className="workspace-page-header">
      <div>
        <p className="eyebrow">BUSINESS</p>
        <h1>See the clinic <em>clearly.</em></h1>
        <p className="workspace-page-intro">Demand, care, cash, and the operational edges that need attention.</p>
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
        {can("patient.export") && <button className="button button-secondary" disabled={exporting} onClick={() => void exportReport("csv")}>{exporting ? "Exporting…" : "Export CSV"}</button>}
        <button className="button button-secondary" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button>
      </div>
    </div>

    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" onClick={() => void load()}>Try again <span>→</span></button></div>}

    {loading && !report && <div className="dashboard-empty" role="status"><strong>Reading the clinic signal</strong><span>Aggregating only the records in your authorized scope…</span></div>}

    {report && <>
      <div className="report-hero-grid">
        <div className="report-hero-card report-hero-dark"><span className="eyebrow">APPOINTMENTS</span><strong>{appointmentTotal}</strong><p>appointments in the last {report.period_days} days</p></div>
        <div className="report-hero-card"><span className="eyebrow">NEW PATIENTS</span><strong>{report.patients_created}</strong><p>new patient records created</p></div>
        <div className="report-hero-card report-hero-warm"><span className="eyebrow">LEADS</span><strong>{leadTotal}</strong><p>enquiries entering the pipeline</p></div>
      </div>

      <div className="report-grid">
        <section className="surface-card report-card">
          <div className="surface-card-heading"><div><p className="eyebrow">CARE FLOW</p><h2>Appointments by state</h2></div><span className="muted-mono">{report.period_days} DAYS</span></div>
          <div className="report-bars">
            {report.appointments.length === 0 && <div className="dashboard-empty"><strong>No appointment activity</strong><span>There is no activity in this reporting window.</span></div>}
            {report.appointments.map((item) => <div className="report-bar-row" key={item.status}><span>{label(item.status)}</span><div><i style={{ width: `${Math.max((item.count / maxAppointment) * 100, item.count ? 4 : 0)}%` }} /></div><b>{item.count}</b></div>)}
          </div>
        </section>

        <section className="surface-card report-card">
          <div className="surface-card-heading"><div><p className="eyebrow">DEMAND</p><h2>Lead pipeline</h2></div><span className="muted-mono">{leadTotal} TOTAL</span></div>
          <div className="report-list">
            {report.leads.length === 0 && <div className="dashboard-empty"><strong>No lead activity</strong><span>New enquiries will appear here as they arrive.</span></div>}
            {report.leads.map((item) => <div className="report-list-row" key={item.status}><span className={`pipeline-status status-${item.status}`}>{label(item.status)}</span><strong>{item.count}</strong></div>)}
          </div>
        </section>
      </div>

      <div className="report-grid">
        <section className="surface-card report-card">
          <div className="surface-card-heading"><div><p className="eyebrow">OPERATIONAL HEALTH</p><h2>Where attention is due</h2></div></div>
          <div className="report-health-grid">
            <div><strong>{report.operational.waiting_patients}</strong><span>waiting patients</span></div>
            <div><strong>{report.operational.followups_due}</strong><span>follow-ups due</span></div>
            <div><strong>{report.operational.no_shows}</strong><span>no-shows</span></div>
            <div><strong>{report.operational.low_inventory}</strong><span>low-stock items</span></div>
          </div>
        </section>

        <section className="surface-card report-card">
          <div className="surface-card-heading"><div><p className="eyebrow">CASH POSITION</p><h2>Collected and open</h2></div><span className="muted-mono">AUTHORIZED VIEW</span></div>
          {report.financial ? <div className="report-finance">
            <div><span>Paid</span><strong>{money(report.financial.paid_minor)}</strong></div>
            <div><span>Outstanding</span><strong>{money(report.financial.outstanding_minor)}</strong></div>
            <small>{report.financial.invoices} invoices issued in this window.</small>
            <div className="report-mini-list"><strong>Payment methods</strong>{report.financial.payment_methods.map((item) => <span key={item.method}>{label(item.method)} · {money(item.paid_minor)}</span>)}</div>
            <div className="report-mini-list"><strong>Outstanding aging</strong>{report.financial.aging.map((item) => <span key={item.bucket}>{label(item.bucket)} · {money(item.outstanding_minor)}</span>)}</div>
          </div> : <div className="dashboard-empty"><strong>Financial data restricted</strong><span>Your role does not include billing.read.</span></div>}
        </section>
      </div>

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

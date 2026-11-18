"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, errorMessage } from "../_lib/client";
import { useToast } from "../_lib/toast";
import { useClinicCurrency } from "../_lib/clinic-context";

type Pair = { current: number; prior: number };
type Kpis = { appointments: Pair; appointments_completed: Pair; no_shows: Pair; new_patients: Pair; leads: Pair; conversions: Pair; paid_minor?: Pair; invoiced_minor?: Pair; patients_billed?: Pair };
type Financial = { invoices: number; invoiced_minor: number; outstanding_minor: number; outstanding_all_minor: number; paid_minor: number; collected_minor: number; refunds_minor: number; net_collected_minor: number; payment_methods: { method: string; payments: number; paid_minor: number }[]; aging: { bucket: string; invoices: number; outstanding_minor: number }[] };
type QueueStats = { arrivals: number; completed: number; cancelled: number; waiting_now: number; in_service_now: number; backlog: number; avg_wait_seconds: number; wait_samples: number };
type FollowUpHealth = { overdue: number; due_today: number; upcoming: number; completed: number };
type InventoryHealth = { tracked: number; in_stock: number; low_stock: number; out_of_stock: number };
type Report = { period_days: number; appointments: { status: string; count: number }[]; patients_created: number; leads: { status: string; count: number }[]; kpis: Kpis; financial: Financial | null; queue: QueueStats; package_utilization: { packages: number; sessions_purchased: number; sessions_used: number; sessions_remaining: number }; operational: { waiting_patients: number; followups_due: number; no_shows: number; low_inventory: number; followups: FollowUpHealth; inventory: InventoryHealth } };
type Branch = { id: string; name: string };
type Session = { permissions?: string[] };
type DailyStat = { date: string; appointments: number; new_patients: number; revenue_minor: number; no_shows: number };
type ChannelStat = { channel: string; leads: number; converted: number };
type FunnelStep = { stage: string; count: number };
type TopService = { name: string; count: number; revenue_minor: number };

const label = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const shortDate = (iso: string) => new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(new Date(iso));
const channelColors = ["#274c42", "#3d7a6a", "#5ba894", "#8cc5b3", "#b84f38", "#d4795e"];
// The chart endpoints take 7d/30d/90d/365d; map the report window onto that.
const rangeForDays = (value: string) => (value === "7" ? "7d" : value === "90" ? "90d" : value === "365" ? "365d" : "30d");
const money = (minor: number, currency: string) => new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(minor / 100);
const rate = (num: number, den: number) => (den > 0 ? num / den : 0);
const duration = (s: number) => (s >= 3600 ? `${Math.round(s / 3600)}h ${Math.round((s % 3600) / 60)}m` : s >= 60 ? `${Math.round(s / 60)}m` : `${Math.round(s)}s`);
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
  const [section, setSection] = useState<"trends" | "care" | "demand" | "cash" | "ops">("trends");
  const [daily, setDaily] = useState<DailyStat[]>([]);
  const [channels, setChannels] = useState<ChannelStat[]>([]);
  const [funnel, setFunnel] = useState<FunnelStep[]>([]);
  const [topServices, setTopServices] = useState<TopService[]>([]);
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
      // Trend charts are clinic-wide (the chart endpoints take no branch) and must not fail the
      // summary, so they load separately and tolerate partial failure.
      const range = rangeForDays(days);
      const charts = await Promise.allSettled([
        api<DailyStat[]>(`/api/v1/operations/analytics/daily?range=${range}`),
        api<ChannelStat[]>(`/api/v1/operations/analytics/channels?range=${range}`),
        api<FunnelStep[]>(`/api/v1/operations/analytics/funnel?range=${range}`),
        api<TopService[]>(`/api/v1/operations/analytics/top-services?range=${range}`),
      ]);
      const val = <T,>(r: PromiseSettledResult<T | null>, fb: T): T => (r.status === "fulfilled" ? (r.value ?? fb) : fb);
      setDaily(val(charts[0], [])); setChannels(val(charts[1], [])); setFunnel(val(charts[2], [])); setTopServices(val(charts[3], []));
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
      rows.push(["financial", "collected", "", String(report.financial.collected_minor)]);
      rows.push(["financial", "refunds", "", String(report.financial.refunds_minor)]);
      rows.push(["financial", "net_collected", "", String(report.financial.net_collected_minor)]);
      rows.push(["financial", "outstanding_window", "", String(report.financial.outstanding_minor)]);
      rows.push(["financial", "outstanding_all_open", "", String(report.financial.outstanding_all_minor)]);
      report.financial.payment_methods.forEach((m) => rows.push(["payment_method", m.method, String(m.payments), String(m.paid_minor)]));
      report.financial.aging.forEach((b) => rows.push(["aging", b.bucket, String(b.invoices), String(b.outstanding_minor)]));
    }
    Object.entries(report.queue).forEach(([k, v]) => rows.push(["queue", k, String(v), ""]));
    Object.entries(report.package_utilization).forEach(([k, v]) => rows.push(["packages", k, String(v), ""]));
    (["waiting_patients", "followups_due", "no_shows", "low_inventory"] as const).forEach((k) => rows.push(["operational", k, String(report.operational[k]), ""]));
    Object.entries(report.operational.followups).forEach(([k, v]) => rows.push(["followups", k, String(v), ""]));
    Object.entries(report.operational.inventory).forEach(([k, v]) => rows.push(["inventory", k, String(v), ""]));
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
  const chartMax = useMemo(() => Math.max(1, ...daily.map((d) => d.appointments)), [daily]);
  const funnelMax = useMemo(() => Math.max(1, ...funnel.map((f) => f.count)), [funnel]);
  const totalLeads = useMemo(() => channels.reduce((sum, c) => sum + c.leads, 0), [channels]);
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
        <p className="workspace-page-intro">Trends, demand, care, cash, and the operational edges that need attention — one view.</p>
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

      {branchId && <p className="report-branch-note">New patients, cash position, packages, queue demand, follow-ups and the trend charts are clinic-wide — those records carry no branch, so the branch filter does not change them. Appointments, leads and inventory are branch-filtered.</p>}

      <div className="pipeline-toolbar"><div className="pipeline-tabs" role="tablist" aria-label="Report sections">
        <button role="tab" aria-selected={section === "trends"} className={section === "trends" ? "active" : ""} onClick={() => setSection("trends")}>Trends</button>
        <button role="tab" aria-selected={section === "care"} className={section === "care" ? "active" : ""} onClick={() => setSection("care")}>Care Flow</button>
        <button role="tab" aria-selected={section === "demand"} className={section === "demand" ? "active" : ""} onClick={() => setSection("demand")}>Demand</button>
        <button role="tab" aria-selected={section === "cash"} className={section === "cash" ? "active" : ""} onClick={() => setSection("cash")}>Cash Position</button>
        <button role="tab" aria-selected={section === "ops"} className={section === "ops" ? "active" : ""} onClick={() => setSection("ops")}>Operational Health</button>
      </div></div>

      {section === "trends" && <>
        <section className="surface-card report-card">
          <div className="surface-card-heading"><div><p className="eyebrow">TRENDS</p><h2>Daily appointments</h2></div><span className="muted-mono">{report.period_days} DAYS</span></div>
          {daily.length === 0
            ? <div className="dashboard-empty"><strong>{loading ? "Loading chart data…" : "No data for this period"}</strong></div>
            : <div className="bar-chart" role="img" aria-label="Daily appointments chart">
              {daily.map((d, i) => <div key={d.date} className="chart-bar" style={{ height: `${Math.max(4, (d.appointments / chartMax) * 100)}%` }}>
                <span className="chart-bar-value">{d.appointments}</span>
                {(i === 0 || i === daily.length - 1 || i % Math.max(1, Math.floor(daily.length / 7)) === 0) && <span className="chart-bar-label">{shortDate(d.date)}</span>}
              </div>)}
            </div>}
        </section>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <section className="surface-card report-card">
            <div className="surface-card-heading"><div><p className="eyebrow">DEMAND</p><h2>Conversion funnel</h2></div></div>
            {funnel.length === 0
              ? <div className="dashboard-empty"><strong>{loading ? "Loading…" : "No funnel data"}</strong></div>
              : <div className="funnel-chart">{funnel.map((step) => <div className="funnel-step" key={step.stage}><span className="funnel-label">{label(step.stage)}</span><div className="funnel-bar" style={{ width: `${Math.max(8, (step.count / funnelMax) * 100)}%` }}><span>{step.count}</span></div></div>)}</div>}
          </section>
          <section className="surface-card report-card">
            <div className="surface-card-heading"><div><p className="eyebrow">ACQUISITION</p><h2>Lead channels</h2></div></div>
            {channels.length === 0
              ? <div className="dashboard-empty"><strong>{loading ? "Loading…" : "No channel data"}</strong></div>
              : <>
                <div className="donut-chart"><svg viewBox="0 0 36 36" style={{ width: "100%", height: "100%", transform: "rotate(-90deg)" }}>{(() => { let offset = 0; return channels.map((ch, i) => { const pct = totalLeads > 0 ? (ch.leads / totalLeads) * 100 : 0; const el = <circle key={ch.channel} cx="18" cy="18" r="15.5" fill="none" stroke={channelColors[i % channelColors.length]} strokeWidth="5" strokeDasharray={`${pct} ${100 - pct}`} strokeDashoffset={-offset} />; offset += pct; return el; }); })()}</svg><div className="donut-center"><strong>{totalLeads}</strong><small>leads</small></div></div>
                <div className="donut-legend">{channels.map((ch, i) => <span key={ch.channel}><i style={{ background: channelColors[i % channelColors.length] }} />{ch.channel} ({ch.leads})</span>)}</div>
              </>}
          </section>
        </div>
        <section className="surface-card report-card">
          <div className="surface-card-heading"><div><p className="eyebrow">PERFORMANCE</p><h2>Top services</h2></div><span className="muted-mono">{topServices.length} SERVICE{topServices.length !== 1 ? "S" : ""}</span></div>
          {topServices.length === 0
            ? <div className="dashboard-empty"><strong>{loading ? "Loading…" : "No service data"}</strong></div>
            : <div className="invoice-list">{topServices.map((s, i) => <article className="invoice-row" key={s.name}><div className="invoice-mark" style={{ fontSize: "0.85rem", fontWeight: 600 }}>#{i + 1}</div><div className="invoice-main"><h3>{s.name}</h3><p>{s.count} appointment{s.count !== 1 ? "s" : ""} · {money(s.revenue_minor, clinicCurrency)} revenue</p></div><div style={{ display: "flex", alignItems: "center", gap: 8 }}><div style={{ width: 80, height: 6, background: "var(--line)", borderRadius: 3, overflow: "hidden" }}><div style={{ width: `${Math.max(5, (s.count / Math.max(1, topServices[0]?.count ?? 1)) * 100)}%`, height: "100%", background: "linear-gradient(90deg,#274c42,#3d7a6a)", borderRadius: 3 }} /></div></div></article>)}</div>}
        </section>
      </>}

      {section === "care" && <section className="surface-card report-card">
        <div className="surface-card-heading"><div><p className="eyebrow">CARE FLOW</p><h2>Appointments by state</h2></div><span className="muted-mono">{report.period_days} DAYS</span></div>
        <div className="report-bars">
          {report.appointments.length === 0 && <div className="dashboard-empty"><strong>No appointment activity</strong><span>There is no activity in this reporting window.</span></div>}
          {report.appointments.map((item) => <div className="report-bar-row" key={item.status}><span>{label(item.status)}</span><div><i style={{ width: `${Math.max((item.count / maxAppointment) * 100, item.count ? 4 : 0)}%` }} /></div><b>{item.count}</b></div>)}
        </div>
        <div className="report-card-links"><Link className="text-link" href="/schedule">Open Schedule <span>↗</span></Link></div>
      </section>}

      {section === "demand" && <section className="surface-card report-card">
        <div className="surface-card-heading"><div><p className="eyebrow">DEMAND</p><h2>Queue activity</h2></div><span className="muted-mono">{report.queue.backlog} IN QUEUE NOW</span></div>
        <div className="report-health-grid">
          <div><strong className={report.queue.backlog > 0 ? "report-warn" : ""}>{report.queue.backlog}</strong><span>current backlog</span></div>
          <div><strong>{report.queue.waiting_now}</strong><span>waiting now</span></div>
          <div><strong>{report.queue.in_service_now}</strong><span>in consultation</span></div>
          <div><strong>{report.queue.arrivals}</strong><span>arrivals · {report.period_days}d</span></div>
          <div><strong>{report.queue.completed}</strong><span>seen · {report.period_days}d</span></div>
          <div><strong>{report.queue.cancelled}</strong><span>left queue · {report.period_days}d</span></div>
          <div><strong>{report.queue.wait_samples > 0 ? duration(report.queue.avg_wait_seconds) : "—"}</strong><span>{report.queue.wait_samples > 0 ? `avg wait to be seen (${report.queue.wait_samples})` : "avg wait · no data"}</span></div>
        </div>
        <small className="report-section-note">Live patient flow from the reception queue — not planned appointments. Backlog is point-in-time; arrivals, seen and left-queue cover the selected window by check-in date.</small>
        <div className="report-card-links"><Link className="text-link" href="/queue">Open Queue <span>↗</span></Link></div>
      </section>}

      {section === "cash" && <section className="surface-card report-card">
        <div className="surface-card-heading"><div><p className="eyebrow">CASH POSITION</p><h2>Collected and open</h2></div><span className="muted-mono">AUTHORIZED VIEW</span></div>
        {report.financial ? <div className="report-finance">
          <div><span>Collected · this period</span><strong>{money(report.financial.collected_minor, clinicCurrency)}</strong></div>
          <div><span>Refunds · this period</span><strong className={report.financial.refunds_minor > 0 ? "report-warn" : ""}>{money(report.financial.refunds_minor, clinicCurrency)}</strong></div>
          <div><span>Net collected · this period</span><strong>{money(report.financial.net_collected_minor, clinicCurrency)}</strong></div>
          <div><span>Outstanding · all open</span><strong>{money(report.financial.outstanding_all_minor, clinicCurrency)}</strong></div>
          <small>Collected counts successful payments by payment date; net collected subtracts refunds recorded in this window. {report.financial.invoices} invoices issued in this window; outstanding and the aging buckets below cover every open invoice.</small>
          <div className="report-mini-list"><strong>Payment methods</strong>{report.financial.payment_methods.map((item) => <span key={item.method}>{label(item.method)} · {money(item.paid_minor, clinicCurrency)}</span>)}</div>
          <div className="report-mini-list"><strong>Outstanding aging</strong>{report.financial.aging.map((item) => <span key={item.bucket}>{label(item.bucket)} · {money(item.outstanding_minor, clinicCurrency)}</span>)}</div>
        </div> : <div className="dashboard-empty"><strong>Financial data restricted</strong><span>Your role does not include billing.read.</span></div>}
        <div className="report-card-links"><Link className="text-link" href="/billing">Open Billing <span>↗</span></Link><Link className="text-link" href="/finance">Open Finance <span>↗</span></Link></div>
      </section>}

      {section === "ops" && (() => {
        const fu = report.operational.followups;
        const fuOpen = fu.overdue + fu.due_today + fu.upcoming;
        const fuCompletion = rate(fu.completed, fu.completed + fuOpen);
        const inv = report.operational.inventory;
        const leadBy = (s: string) => report.leads.find((l) => l.status === s)?.count ?? 0;
        const needsAttention = leadBy("new") + leadBy("contacted");
        return <>
          <section className="surface-card report-card">
            <div className="surface-card-heading"><div><p className="eyebrow">OPERATIONAL HEALTH · FOLLOW-UPS</p><h2>Follow-up tasks</h2></div><span className="muted-mono">{pctFmt(fuCompletion)} DONE</span></div>
            <div className="report-health-grid">
              <div><strong className={fu.overdue > 0 ? "report-warn" : ""}>{fu.overdue}</strong><span>overdue</span></div>
              <div><strong>{fu.due_today}</strong><span>due today</span></div>
              <div><strong>{fu.upcoming}</strong><span>upcoming</span></div>
              <div><strong>{fu.completed}</strong><span>completed · {report.period_days}d</span></div>
            </div>
            <small className="report-section-note">Open tasks by actual due date; overdue means the due date has passed and the task is still open. Clinic-wide — follow-ups carry no branch.</small>
            <div className="report-card-links"><Link className="text-link" href="/operations">Open Follow-ups <span>↗</span></Link><Link className="text-link" href="/operations?status=completed">Completed <span>↗</span></Link></div>
          </section>
          <section className="surface-card report-card">
            <div className="surface-card-heading"><div><p className="eyebrow">OPERATIONAL HEALTH · LEADS</p><h2>Lead pipeline</h2></div><span className="muted-mono">{leadTotal} TOTAL</span></div>
            {report.leads.length === 0
              ? <div className="dashboard-empty"><strong>No lead activity</strong><span>New enquiries will appear here as they arrive.</span></div>
              : <div className="report-health-grid">
                <div><strong className={needsAttention > 0 ? "report-warn" : ""}>{needsAttention}</strong><span>need attention</span></div>
                <div><strong>{leadBy("qualified")}</strong><span>qualified</span></div>
                <div><strong>{report.kpis.conversions.current}</strong><span>converted</span></div>
                <div><strong>{leadBy("lost")}</strong><span>lost</span></div>
                <div><strong>{kpiView?.conversion.value ?? "—"}</strong><span>conversion rate</span></div>
              </div>}
            <small className="report-section-note">A lead counts as converted once it is linked to a patient. &ldquo;Need attention&rdquo; is new and contacted leads not yet qualified.</small>
            <div className="report-card-links"><Link className="text-link" href="/leads">Open Leads <span>↗</span></Link><Link className="text-link" href="/leads?status=qualified">Qualified <span>↗</span></Link><Link className="text-link" href="/leads?status=lost">Lost <span>↗</span></Link></div>
          </section>
          <section className="surface-card report-card">
            <div className="surface-card-heading"><div><p className="eyebrow">OPERATIONAL HEALTH · INVENTORY</p><h2>Stock levels</h2></div><span className="muted-mono">{inv.tracked} TRACKED</span></div>
            <div className="report-health-grid">
              <div><strong>{inv.in_stock}</strong><span>in stock</span></div>
              <div><strong className={inv.low_stock > 0 ? "report-warn" : ""}>{inv.low_stock}</strong><span>low stock</span></div>
              <div><strong className={inv.out_of_stock > 0 ? "report-warn" : ""}>{inv.out_of_stock}</strong><span>out of stock</span></div>
            </div>
            <small className="report-section-note">On-hand stock per branch-product against each product&rsquo;s reorder threshold. Low excludes out-of-stock; the schema tracks no reservations or expiry.</small>
            <div className="report-card-links"><Link className="text-link" href="/inventory">Open Inventory <span>↗</span></Link></div>
          </section>
        </>;
      })()}

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

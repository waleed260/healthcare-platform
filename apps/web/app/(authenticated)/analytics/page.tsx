"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import anime from "animejs";
import { api, errorMessage } from "../_lib/client";
import { useToast } from "../_lib/toast";

type Session = { permissions?: string[] };
type DailyStat = { date: string; appointments: number; new_patients: number; revenue_minor: number; no_shows: number };
type ChannelStat = { channel: string; leads: number; converted: number };
type FunnelStep = { stage: string; count: number };
type TopService = { name: string; count: number; revenue_minor: number };

const RANGES = [
  { id: "7d", label: "7 days" },
  { id: "30d", label: "30 days" },
  { id: "90d", label: "90 days" },
] as const;
type Range = (typeof RANGES)[number]["id"];

function money(minor: number): string {
  return new Intl.NumberFormat(undefined, { style: "currency", currency: "PKR", minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(minor / 100);
}

function shortDate(iso: string): string {
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(new Date(iso));
}

function pctChange(current: number, previous: number): { label: string; up: boolean } {
  if (previous === 0) return { label: current > 0 ? "+100%" : "0%", up: current > 0 };
  const pct = Math.round(((current - previous) / previous) * 100);
  return { label: `${pct >= 0 ? "+" : ""}${pct}%`, up: pct >= 0 };
}

export default function AnalyticsPage() {
  const [range, setRange] = useState<Range>("30d");
  const [daily, setDaily] = useState<DailyStat[]>([]);
  const [channels, setChannels] = useState<ChannelStat[]>([]);
  const [funnel, setFunnel] = useState<FunnelStep[]>([]);
  const [topServices, setTopServices] = useState<TopService[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  const chartRef = useRef<HTMLDivElement>(null);
  const cardsRef = useRef<HTMLDivElement>(null);
  const funnelRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [dailyData, channelData, funnelData, serviceData] = await Promise.all([
        api<DailyStat[]>(`/api/v1/operations/analytics/daily?range=${range}`).catch(() => [] as DailyStat[]),
        api<ChannelStat[]>(`/api/v1/operations/analytics/channels?range=${range}`).catch(() => [] as ChannelStat[]),
        api<FunnelStep[]>(`/api/v1/operations/analytics/funnel?range=${range}`).catch(() => [] as FunnelStep[]),
        api<TopService[]>(`/api/v1/operations/analytics/top-services?range=${range}`).catch(() => [] as TopService[]),
      ]);
      setDaily(dailyData ?? []);
      setChannels(channelData ?? []);
      setFunnel(funnelData ?? []);
      setTopServices(serviceData ?? []);
    } catch (reason) {
      setError(errorMessage(reason, "Analytics could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, [range]);
  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (loading) return;
    if (cardsRef.current) {
      anime({
        targets: cardsRef.current.querySelectorAll(".analytics-card"),
        opacity: [0, 1],
        translateY: [28, 0],
        scale: [0.93, 1],
        duration: 600,
        delay: anime.stagger(70, { start: 80 }),
        easing: "easeOutExpo",
      });
    }
    if (chartRef.current) {
      anime({
        targets: chartRef.current.querySelectorAll(".chart-bar"),
        scaleY: [0, 1],
        duration: 650,
        delay: anime.stagger(40, { start: 300 }),
        easing: "easeOutCubic",
      });
    }
    if (funnelRef.current) {
      anime({
        targets: funnelRef.current.querySelectorAll(".funnel-bar"),
        width: (el: HTMLElement) => [0, el.style.width || "100%"],
        opacity: [0, 1],
        duration: 700,
        delay: anime.stagger(100, { start: 400 }),
        easing: "easeOutCubic",
      });
    }
  }, [loading, range]);

  const totals = useMemo(() => {
    const half = Math.floor(daily.length / 2);
    const recent = daily.slice(half);
    const prior = daily.slice(0, half);
    const sum = (arr: DailyStat[], key: keyof DailyStat) => arr.reduce((s, d) => s + (d[key] as number), 0);
    return {
      appointments: sum(daily, "appointments"),
      appointmentsTrend: pctChange(sum(recent, "appointments"), sum(prior, "appointments")),
      newPatients: sum(daily, "new_patients"),
      newPatientsTrend: pctChange(sum(recent, "new_patients"), sum(prior, "new_patients")),
      revenue: sum(daily, "revenue_minor"),
      revenueTrend: pctChange(sum(recent, "revenue_minor"), sum(prior, "revenue_minor")),
      noShows: sum(daily, "no_shows"),
      noShowsTrend: pctChange(sum(recent, "no_shows"), sum(prior, "no_shows")),
    };
  }, [daily]);

  const chartMax = useMemo(() => Math.max(1, ...daily.map((d) => d.appointments)), [daily]);

  const funnelMax = useMemo(() => Math.max(1, ...funnel.map((f) => f.count)), [funnel]);

  const totalLeads = useMemo(() => channels.reduce((s, c) => s + c.leads, 0), [channels]);
  const channelColors = ["#274c42", "#3d7a6a", "#5ba894", "#8cc5b3", "#b84f38", "#d4795e"];

  return <main className="workspace-page analytics-page">
    <div className="workspace-page-header">
      <div>
        <p className="eyebrow">INSIGHTS · PERFORMANCE</p>
        <h1>Know your <em>numbers.</em></h1>
        <p className="workspace-page-intro">Track appointments, revenue, patient acquisition, and conversion across your clinic.</p>
      </div>
      <div className="header-actions">
        <div className="pipeline-tabs" role="tablist">
          {RANGES.map((r) => <button key={r.id} role="tab" aria-selected={range === r.id} className={range === r.id ? "active" : ""} onClick={() => setRange(r.id)}>{r.label}</button>)}
        </div>
        <button className="button button-secondary" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button>
      </div>
    </div>

    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" onClick={() => void load()}>Try again <span>→</span></button></div>}

    {/* KPI cards */}
    <div className="analytics-grid" ref={cardsRef}>
      <div className="analytics-card">
        <p className="eyebrow">APPOINTMENTS</p>
        <strong>{totals.appointments.toLocaleString()}</strong>
        <small className={totals.appointmentsTrend.up ? "trend-up" : "trend-down"}>{totals.appointmentsTrend.label} vs prior period</small>
      </div>
      <div className="analytics-card">
        <p className="eyebrow">NEW PATIENTS</p>
        <strong>{totals.newPatients.toLocaleString()}</strong>
        <small className={totals.newPatientsTrend.up ? "trend-up" : "trend-down"}>{totals.newPatientsTrend.label} vs prior period</small>
      </div>
      <div className="analytics-card">
        <p className="eyebrow">REVENUE</p>
        <strong>{money(totals.revenue)}</strong>
        <small className={totals.revenueTrend.up ? "trend-up" : "trend-down"}>{totals.revenueTrend.label} vs prior period</small>
      </div>
      <div className="analytics-card">
        <p className="eyebrow">NO-SHOWS</p>
        <strong>{totals.noShows.toLocaleString()}</strong>
        <small className={totals.noShowsTrend.up ? "trend-down" : "trend-up"}>{totals.noShowsTrend.label} vs prior period</small>
      </div>
    </div>

    {/* Appointments chart */}
    <div className="analytics-chart" ref={chartRef}>
      <h3>Daily appointments</h3>
      {daily.length === 0
        ? <div className="dashboard-empty"><strong>{loading ? "Loading chart data…" : "No data for this period"}</strong></div>
        : <div className="bar-chart" role="img" aria-label="Daily appointments chart">
          {daily.map((d, i) => <div key={d.date} className="chart-bar" style={{ height: `${Math.max(4, (d.appointments / chartMax) * 100)}%` }}>
            <span className="chart-bar-value">{d.appointments}</span>
            {(i === 0 || i === daily.length - 1 || i % Math.max(1, Math.floor(daily.length / 7)) === 0) && <span className="chart-bar-label">{shortDate(d.date)}</span>}
          </div>)}
        </div>}
    </div>

    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
      {/* Conversion funnel */}
      <div className="analytics-chart" ref={funnelRef}>
        <h3>Conversion funnel</h3>
        {funnel.length === 0
          ? <div className="dashboard-empty"><strong>{loading ? "Loading…" : "No funnel data"}</strong></div>
          : <div className="funnel-chart">
            {funnel.map((step) => <div className="funnel-step" key={step.stage}>
              <span className="funnel-label">{step.stage}</span>
              <div className="funnel-bar" style={{ width: `${Math.max(8, (step.count / funnelMax) * 100)}%` }}>
                <span>{step.count}</span>
              </div>
            </div>)}
          </div>}
      </div>

      {/* Acquisition channels donut */}
      <div className="analytics-chart">
        <h3>Lead channels</h3>
        {channels.length === 0
          ? <div className="dashboard-empty"><strong>{loading ? "Loading…" : "No channel data"}</strong></div>
          : <>
            <div className="donut-chart">
              <svg viewBox="0 0 36 36" style={{ width: "100%", height: "100%", transform: "rotate(-90deg)" }}>
                {(() => {
                  let offset = 0;
                  return channels.map((ch, i) => {
                    const pct = totalLeads > 0 ? (ch.leads / totalLeads) * 100 : 0;
                    const el = <circle key={ch.channel} cx="18" cy="18" r="15.5" fill="none" stroke={channelColors[i % channelColors.length]} strokeWidth="5" strokeDasharray={`${pct} ${100 - pct}`} strokeDashoffset={-offset} style={{ transition: "stroke-dasharray .8s ease" }} />;
                    offset += pct;
                    return el;
                  });
                })()}
              </svg>
              <div className="donut-center">
                <strong>{totalLeads}</strong>
                <small>leads</small>
              </div>
            </div>
            <div className="donut-legend">
              {channels.map((ch, i) => <span key={ch.channel}><i style={{ background: channelColors[i % channelColors.length] }} />{ch.channel} ({ch.leads})</span>)}
            </div>
          </>}
      </div>
    </div>

    {/* Top services table */}
    <section className="surface-card" style={{ marginTop: 16 }}>
      <div className="surface-card-heading">
        <div><p className="eyebrow">PERFORMANCE</p><h2>Top services</h2></div>
        <span className="muted-mono">{topServices.length} SERVICE{topServices.length !== 1 ? "S" : ""}</span>
      </div>
      {topServices.length === 0
        ? <div className="dashboard-empty"><strong>{loading ? "Loading…" : "No service data"}</strong></div>
        : <div className="invoice-list">
          {topServices.map((s, i) => <article className="invoice-row" key={s.name}>
            <div className="invoice-mark" style={{ fontSize: "0.85rem", fontWeight: 600 }}>#{i + 1}</div>
            <div className="invoice-main">
              <h3>{s.name}</h3>
              <p>{s.count} appointment{s.count !== 1 ? "s" : ""} · {money(s.revenue_minor)} revenue</p>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{ width: 80, height: 6, background: "var(--line)", borderRadius: 3, overflow: "hidden" }}>
                <div style={{ width: `${Math.max(5, (s.count / Math.max(1, topServices[0]?.count ?? 1)) * 100)}%`, height: "100%", background: "linear-gradient(90deg,#274c42,#3d7a6a)", borderRadius: 3, transition: "width .6s ease" }} />
              </div>
              <span className="muted-mono" style={{ fontSize: "0.72rem" }}>{money(s.revenue_minor)}</span>
            </div>
          </article>)}
        </div>}
    </section>
  </main>;
}

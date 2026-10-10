"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import anime from "animejs";
import PremiumMotion from "../../premium-motion";
import AddAppointmentDrawer from "../_lib/add-appointment-drawer";

type Summary = { today_appointments: number; pending_approvals: number; followups_due: number; waiting_patients: number; no_shows: number };
type Appointment = { id: string; reference: string; starts_at: string; ends_at: string; status: string };
type QueueEntry = { id: string; appointment_id: string; status: string; checked_in_at: string | null; priority: number; full_name: string; reference: string; starts_at: string };
type FollowUp = { id: string; patient_id: string; reason: string; due_at: string; priority: number; status: string };
type Session = { permissions?: string[]; clinic_slug?: string | null };

function msg(response: Response, payload: unknown): string {
  if (payload && typeof payload === "object" && "error" in payload) {
    const m = (payload as { error?: { message?: string } }).error?.message;
    if (m) return m;
  }
  if (response.status === 401) return "Your clinic session has expired. Sign in again to continue.";
  return "The workspace could not be loaded. Try again shortly.";
}
const time = (v: string) => new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date(v));
const dayShort = (v: string) => new Intl.DateTimeFormat(undefined, { weekday: "short" }).format(new Date(v));
async function getData<T>(url: string): Promise<T | null> {
  try {
    const r = await fetch(url, { credentials: "include", cache: "no-store" });
    if (r.status === 401) { window.location.href = "/login"; return null; }
    if (!r.ok) return null;
    const p = (await r.json().catch(() => null)) as { data?: T } | null;
    return (p?.data ?? null) as T | null;
  } catch { return null; }
}
const statusClass = (s: string) => `pipeline-status status-${s.replaceAll("_", "-")}`;

export default function DashboardPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [queue, setQueue] = useState<QueueEntry[]>([]);
  const [followups, setFollowups] = useState<FollowUp[]>([]);
  const [requests, setRequests] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [clinicSlug, setClinicSlug] = useState("");
  const [addApptOpen, setAddApptOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [sessionData, summaryResponse] = await Promise.all([
        getData<Session>("/api/v1/auth/me"),
        fetch("/api/v1/operations/dashboard-summary", { credentials: "include", cache: "no-store" }),
      ]);
      if (sessionData) {
        setPermissions(sessionData.permissions ?? []);
        if (sessionData.clinic_slug) setClinicSlug(sessionData.clinic_slug);
      }
      if (summaryResponse.status === 401) { window.location.href = "/login"; return; }
      const summaryPayload = (await summaryResponse.json().catch(() => null)) as { data?: Summary } | null;
      if (!summaryResponse.ok) throw new Error(msg(summaryResponse, summaryPayload));
      setSummary(summaryPayload?.data ?? null);
      const [appts, requested, q, f] = await Promise.all([
        getData<Appointment[]>("/api/v1/appointments?limit=100"),
        getData<Appointment[]>("/api/v1/appointments?status=requested&limit=10"),
        getData<QueueEntry[]>("/api/v1/operations/queue"),
        getData<FollowUp[]>("/api/v1/operations/follow-ups?status=due&limit=10"),
      ]);
      setAppointments(appts ?? []);
      setRequests(requested ?? []);
      setQueue(q ?? []); setFollowups(f ?? []);
      setRefreshedAt(new Date());
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The workspace could not be loaded."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const schedule = useMemo(() => [...appointments].sort((a, b) => a.starts_at.localeCompare(b.starts_at)), [appointments]);
  const weekBars = useMemo(() => {
    const labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    const now = new Date();
    const dayOfWeek = (now.getDay() + 6) % 7;
    const weekStart = new Date(now.getFullYear(), now.getMonth(), now.getDate() - dayOfWeek);
    const weekEnd = new Date(weekStart.getTime() + 7 * 86400000);
    const thisWeek = appointments.filter((a) => { const d = new Date(a.starts_at); return d >= weekStart && d < weekEnd; });
    const counts = new Map<string, number>(labels.map((l) => [l, 0]));
    for (const a of thisWeek) { const d = dayShort(a.starts_at); if (counts.has(d)) counts.set(d, (counts.get(d) ?? 0) + 1); }
    const values = labels.map((l) => counts.get(l) ?? 0);
    const max = Math.max(1, ...values);
    return labels.map((l, i) => ({ label: l, value: values[i], pct: Math.round((values[i] / max) * 100) }));
  }, [appointments]);

  const kpi = (value: number | undefined) => (loading && summary === null ? "…" : value ?? "—");

  const kpiRef = useRef<HTMLDivElement>(null);
  const mainRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (loading || !summary) return;
    if (kpiRef.current) {
      anime({
        targets: kpiRef.current.querySelectorAll(".kpi-card"),
        opacity: [0, 1],
        translateY: [24, 0],
        scale: [0.95, 1],
        duration: 550,
        delay: anime.stagger(70, { start: 100 }),
        easing: "easeOutCubic",
      });
    }
    if (mainRef.current) {
      anime({
        targets: mainRef.current.querySelectorAll(".panel-card"),
        opacity: [0, 1],
        translateY: [30, 0],
        duration: 550,
        delay: anime.stagger(90, { start: 350 }),
        easing: "easeOutCubic",
      });
    }
    if (bottomRef.current) {
      anime({
        targets: bottomRef.current.querySelectorAll(".panel-card"),
        opacity: [0, 1],
        translateY: [30, 0],
        duration: 550,
        delay: anime.stagger(90, { start: 550 }),
        easing: "easeOutCubic",
      });
    }
  }, [loading, summary]);

  return <main className="dashboard-overview" id="overview" aria-busy={loading}>
    <PremiumMotion />
    <div className="dash-topline"><div><p className="eyebrow">Today</p><h1>Today at a <em>glance.</em></h1></div><div className="header-actions">{permissions.includes("appointment.create") && <button className="button button-primary" type="button" onClick={() => setAddApptOpen(true)}>Add appointment <span>+</span></button>}<button className="button button-secondary" type="button" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button></div></div>
    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" type="button" onClick={() => void load()}>Try again <span>→</span></button></div>}

    <div className="kpi-grid" ref={kpiRef} aria-live="polite">
      <Link className="kpi-card" href="/schedule"><span className="kpi-ico kpi-ico-blue" aria-hidden="true">📅</span><div><small>Today&apos;s appointments</small><strong>{kpi(summary?.today_appointments)}</strong></div></Link>
      <Link className="kpi-card" href="/queue"><span className="kpi-ico kpi-ico-green" aria-hidden="true">👥</span><div><small>Waiting</small><strong>{kpi(summary?.waiting_patients)}</strong></div></Link>
      <Link className="kpi-card" href="/schedule?status=requested"><span className="kpi-ico kpi-ico-amber" aria-hidden="true">🗎</span><div><small>Pending approval</small><strong>{kpi(summary?.pending_approvals)}</strong></div></Link>
      <Link className="kpi-card" href="/operations"><span className="kpi-ico kpi-ico-rose" aria-hidden="true">✓</span><div><small>Follow-ups due</small><strong>{kpi(summary?.followups_due)}</strong></div></Link>
    </div>

    <div className="dash-main-grid" ref={mainRef}>
      <section className="panel-card" id="schedule"><div className="card-heading"><div><p className="eyebrow">YOUR DAY</p><h2>Today&apos;s schedule</h2></div><Link className="text-link" href="/schedule">View full calendar <span>→</span></Link></div>
        {loading && schedule.length === 0 ? <div className="dashboard-empty" role="status"><strong>Loading schedule…</strong></div> : schedule.length === 0 ? <div className="dashboard-empty"><strong>No appointments</strong><span>Your scoped schedule is clear for now.</span></div> : <div className="dash-table"><div className="dash-table-row dash-table-head"><span>Time</span><span>Appointment</span><span>Status</span></div>{schedule.slice(0, 9).map((a) => <div className="dash-table-row" key={a.id}><time dateTime={a.starts_at}>{time(a.starts_at)}</time><span className="dash-ref"><strong>{a.reference}</strong><small>{time(a.starts_at)}–{time(a.ends_at)}</small></span><span className={statusClass(a.status)}>{a.status.replaceAll("_", " ")}</span></div>)}</div>}
      </section>

      <div className="dash-side-col">
        <section className="panel-card"><div className="card-heading"><div><p className="eyebrow">NOW</p><h2>Live patient queue</h2></div><Link className="text-link" href="/queue">View all <span>→</span></Link></div>
          {loading && queue.length === 0 ? <div className="dashboard-empty" role="status"><strong>Loading…</strong></div> : queue.length === 0 ? <div className="dashboard-empty"><strong>Queue is empty</strong><span>No one is waiting right now.</span></div> : <div className="queue-list">{queue.slice(0, 5).map((e, i) => <div className="queue-row" key={e.id}><span className="queue-num">{String(i + 1).padStart(2, "0")}</span><div className="queue-main"><strong>{e.full_name}</strong><small>{e.checked_in_at ? `in ${time(e.checked_in_at)}` : e.reference}</small></div><span className={`queue-state state-${e.status.replaceAll("_", "-")}`}>{e.status.replaceAll("_", " ")}</span><Link className="queue-action" href="/queue">Start →</Link></div>)}</div>}
        </section>
        <section className="panel-card quick-actions"><div className="card-heading"><div><p className="eyebrow">⚡ QUICK ACTIONS</p><h2>Do it now</h2></div></div><div className="quick-grid"><Link className="quick-btn" href="/schedule">＋ Add appointment <span>→</span></Link><Link className="quick-btn" href="/patients">👤 Add patient <span>→</span></Link><Link className="quick-btn" href="/schedule">⏱ Block time <span>→</span></Link><Link className="quick-btn" href="/operations">🗎 Create follow-up <span>→</span></Link></div></section>
      </div>
    </div>

    <div className="dash-bottom-grid" ref={bottomRef}>
      <section className="panel-card"><div className="card-heading"><div><p className="eyebrow">INBOX</p><h2>Appointment requests</h2></div><Link className="text-link" href="/schedule?status=requested">View all <span>→</span></Link></div>
        {requests.length === 0 ? <div className="dashboard-empty"><strong>No pending requests</strong><span>New booking requests will appear here.</span></div> : <div className="dash-table"><div className="dash-table-row dash-table-head req-row"><span>Reference</span><span>Requested</span><span>Action</span></div>{requests.slice(0, 5).map((a) => <div className="dash-table-row req-row" key={a.id}><strong>{a.reference}</strong><small>{dayShort(a.starts_at)} {time(a.starts_at)}</small><Link className="text-control" href="/schedule?status=requested">Review</Link></div>)}</div>}
      </section>
      <section className="panel-card"><div className="card-heading"><div><p className="eyebrow">DUE</p><h2>Follow-ups due</h2></div><Link className="text-link" href="/operations">View all <span>→</span></Link></div>
        {followups.length === 0 ? <div className="dashboard-empty"><strong>Nothing due</strong><span>Follow-up tasks will appear here.</span></div> : <div className="followup-list">{followups.slice(0, 5).map((f) => <div className="followup-row" key={f.id}><div><strong>{f.reason || "Follow-up"}</strong><small>due {dayShort(f.due_at)} {time(f.due_at)}</small></div><span className={`pipeline-status status-${f.status === "overdue" ? "lost" : "qualified"}`}>{f.status}</span></div>)}</div>}
      </section>
      <section className="panel-card"><div className="card-heading"><div><p className="eyebrow">📊 TREND</p><h2>Appointments this week</h2></div></div><div className="bar-chart" role="img" aria-label="Appointments by weekday">{weekBars.map((b) => <div className="bar-col" key={b.label}><div className="bar-track"><div className="bar-fill" style={{ height: `${b.pct}%` }} title={`${b.label}: ${b.value}`} /></div><small>{b.label}</small><b>{b.value}</b></div>)}</div></section>
    </div>
    {refreshedAt && <p className="stale-note">Updated {refreshedAt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</p>}
    {clinicSlug && <AddAppointmentDrawer open={addApptOpen} onClose={() => setAddApptOpen(false)} clinicSlug={clinicSlug} onCreated={() => void load()} />}
  </main>;
}

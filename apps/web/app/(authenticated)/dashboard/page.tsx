"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import DataTable, { type Column, RowSkeleton } from "../_lib/data-table";
import { api } from "../_lib/client";

const AddAppointmentDrawer = dynamic(() => import("../_lib/add-appointment-drawer"), { ssr: false });
const AddPatientDrawer = dynamic(() => import("../_lib/add-patient-drawer"), { ssr: false });
const BlockTimeDrawer = dynamic(() => import("../_lib/block-time-drawer"), { ssr: false });
const FollowUpDrawer = dynamic(() => import("../_lib/follow-up-drawer"), { ssr: false });

type Summary = { today_appointments: number; pending_approvals: number; followups_due: number; waiting_patients: number; no_shows: number };
type Appointment = { id: string; reference: string; starts_at: string; ends_at: string; status: string };
type QueueEntry = { id: string; appointment_id: string; status: string; checked_in_at: string | null; priority: number; full_name: string; reference: string; starts_at: string };
type FollowUp = { id: string; patient_id: string; reason: string; due_at: string; priority: number; status: string };
type Session = { permissions?: string[]; clinic_slug?: string | null };

const time = (v: string) => new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date(v));
const dayShort = (v: string) => new Intl.DateTimeFormat(undefined, { weekday: "short" }).format(new Date(v));
const todayLabel = new Intl.DateTimeFormat(undefined, { weekday: "long", day: "numeric", month: "long" }).format(new Date());
async function getData<T>(url: string): Promise<T | null> {
  try { return await api<T>(url); } catch { return null; }
}
const statusClass = (s: string) => `pipeline-status status-${s.replaceAll("_", "-")}`;

/* Inline SVG icon set — replaces emoji glyphs for a consistent, premium look. */
function Icon({ children }: { children: ReactNode }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>;
}
const IconCalendar = () => <Icon><rect x="3" y="4" width="18" height="17" rx="2" /><path d="M16 2v4M8 2v4M3 9h18" /></Icon>;
const IconUsers = () => <Icon><circle cx="9" cy="8" r="3.6" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /><path d="M15.5 4.9a3.6 3.6 0 0 1 0 6.2" /><path d="M17.6 14.5a6.5 6.5 0 0 1 4 5.5" /></Icon>;
const IconFile = () => <Icon><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6" /><path d="M9 13h6M9 17h6" /></Icon>;
const IconCheck = () => <Icon><circle cx="12" cy="12" r="9" /><path d="m8.5 12.3 2.4 2.4 4.8-5.2" /></Icon>;
const IconPlus = () => <Icon><path d="M12 5v14M5 12h14" /></Icon>;
const IconUser = () => <Icon><circle cx="12" cy="8" r="4" /><path d="M4.5 21a7.5 7.5 0 0 1 15 0" /></Icon>;
const IconPen = () => <Icon><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></Icon>;
const IconCard = () => <Icon><rect x="2" y="5" width="20" height="14" rx="2" /><path d="M2 10h20" /></Icon>;
const IconChart = () => <Icon><path d="M3 3v18h18" /><path d="M8 17v-6M13 17V7M18 17v-4" /></Icon>;
const IconFlag = () => <Icon><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1Z" /><path d="M4 22v-7" /></Icon>;

const scheduleCols: Column<Appointment>[] = [
  { key: "time", header: "Time", width: "70px", render: (a) => <time dateTime={a.starts_at}>{time(a.starts_at)}</time> },
  { key: "reference", header: "Appointment", width: "1fr", sortable: true, sortFn: (a, b) => a.reference.localeCompare(b.reference), render: (a) => <span className="dash-ref"><strong>{a.reference}</strong><small>{time(a.starts_at)}–{time(a.ends_at)}</small></span> },
  { key: "status", header: "Status", width: "auto", render: (a) => <span className={statusClass(a.status)}>{a.status.replaceAll("_", " ")}</span> },
];

const requestCols: Column<Appointment>[] = [
  { key: "reference", header: "Reference", width: "1fr", render: (a) => <strong>{a.reference}</strong> },
  { key: "requested", header: "Requested", width: "auto", render: (a) => <small>{dayShort(a.starts_at)} {time(a.starts_at)}</small> },
  { key: "action", header: "Action", width: "auto", srOnly: true, render: () => <Link className="text-control" href="/schedule?status=requested">Review</Link> },
];

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
  const [addPatientOpen, setAddPatientOpen] = useState(false);
  const [blockTimeOpen, setBlockTimeOpen] = useState(false);
  const [followUpOpen, setFollowUpOpen] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [sessionData, summaryData, appts, requested, q, f] = await Promise.all([
        getData<Session>("/api/v1/auth/me"),
        getData<Summary>("/api/v1/operations/dashboard-summary"),
        getData<Appointment[]>("/api/v1/appointments?limit=100"),
        getData<Appointment[]>("/api/v1/appointments?status=requested&limit=10"),
        getData<QueueEntry[]>("/api/v1/operations/queue"),
        getData<FollowUp[]>("/api/v1/operations/follow-ups?status=due&limit=10"),
      ]);
      if (sessionData) {
        setPermissions(sessionData.permissions ?? []);
        if (sessionData.clinic_slug) setClinicSlug(sessionData.clinic_slug);
      }
      setSummary(summaryData);
      setAppointments(appts ?? []);
      setRequests(requested ?? []);
      setQueue(q ?? []); setFollowups(f ?? []);
      setRefreshedAt(new Date());
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not load dashboard."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    const id = setInterval(() => { if (!document.hidden) void load(); }, 300_000);
    const onVisible = () => { if (!document.hidden) void load(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => { clearInterval(id); document.removeEventListener("visibilitychange", onVisible); };
  }, [load]);

  /* Light tick so countdowns and waiting times stay honest between refreshes. */
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);

  const schedule = useMemo(() => {
    const today = new Date();
    const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
    return appointments.filter((a) => a.starts_at.slice(0, 10) === todayStr).sort((a, b) => a.starts_at.localeCompare(b.starts_at));
  }, [appointments]);
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
    return labels.map((l, i) => ({ label: l, value: values[i], pct: Math.round((values[i] / max) * 100), today: i === dayOfWeek }));
  }, [appointments]);

  /* Compare today with the average of the weekdays so far this week. */
  const apptDelta = useMemo(() => {
    const todayIdx = weekBars.findIndex((b) => b.today);
    const prior = weekBars.slice(0, todayIdx).map((b) => b.value);
    if (prior.length === 0 || !prior.some((v) => v > 0)) return null;
    const avg = prior.reduce((a, b) => a + b, 0) / prior.length;
    return Math.round((weekBars[todayIdx]?.value ?? 0) - avg);
  }, [weekBars]);

  const nextUp = useMemo(() => {
    return schedule.find((a) => !["cancelled", "no_show", "no-show", "completed"].includes(a.status) && new Date(a.ends_at).getTime() > now) ?? null;
  }, [schedule, now]);

  const kpi = (value: number | undefined) => (loading && summary === null ? "…" : value ?? "—");

  const nextUpView = (() => {
    if (!nextUp) return null;
    const start = new Date(nextUp.starts_at).getTime();
    const end = new Date(nextUp.ends_at).getTime();
    const live = start <= now && end > now;
    const mins = Math.max(0, Math.round((start - now) / 60000));
    const when = live ? "now" : mins < 60 ? `in ${mins} min` : `in ${Math.round(mins / 60)} h`;
    return <section className="next-up" aria-label="Next appointment">
      <span className="next-up-dot" aria-hidden="true" />
      <div className="next-up-main"><p className="eyebrow">{live ? "HAPPENING NOW" : "NEXT UP"}</p><strong>{nextUp.reference} · {time(nextUp.starts_at)}–{time(nextUp.ends_at)}</strong></div>
      <span className="next-up-count">{when}</span>
      <span className={statusClass(nextUp.status)}>{nextUp.status.replaceAll("_", " ")}</span>
      <Link className="text-control" href="/queue">Queue <span>→</span></Link>
    </section>;
  })();

  return <main className="dashboard-overview" id="overview" aria-busy={loading}>
    <div className="dash-topline"><div><h1>Today</h1><p className="dash-date">{todayLabel}</p></div><div className="header-actions">{permissions.includes("appointment.create") && <button className="button button-primary" type="button" onClick={() => setAddApptOpen(true)}>Book appointment <span>+</span></button>}</div></div>
    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" type="button" onClick={() => void load()}>Try again <span>→</span></button></div>}

    <div className="kpi-grid" aria-live="polite">
      <Link className="kpi-card kpi-card-blue" href="/schedule"><span className="kpi-ico kpi-ico-blue" aria-hidden="true"><IconCalendar /></span><div><small>Appointments</small><strong>{kpi(summary?.today_appointments)}</strong>{apptDelta !== null && <span className={`kpi-delta ${apptDelta >= 0 ? "kpi-delta-up" : "kpi-delta-down"}`}>{apptDelta >= 0 ? "▲" : "▼"} {Math.abs(apptDelta)} vs week avg</span>}</div></Link>
      <Link className="kpi-card kpi-card-green" href="/queue"><span className="kpi-ico kpi-ico-green" aria-hidden="true"><IconUsers /></span><div><small>Waiting</small><strong>{kpi(summary?.waiting_patients)}</strong></div></Link>
      <Link className="kpi-card kpi-card-amber" href="/schedule?status=requested"><span className="kpi-ico kpi-ico-amber" aria-hidden="true"><IconFile /></span><div><small>Pending</small><strong>{kpi(summary?.pending_approvals)}</strong></div></Link>
      <Link className="kpi-card kpi-card-rose" href="/operations"><span className="kpi-ico kpi-ico-rose" aria-hidden="true"><IconCheck /></span><div><small>Follow-ups</small><strong>{kpi(summary?.followups_due)}</strong></div></Link>
    </div>

    {nextUpView}

    <div className="dash-main-grid">
      <section className="panel-card" id="schedule"><div className="card-heading"><div><h2>Schedule</h2></div><Link className="text-link" href="/schedule">Full calendar <span>→</span></Link></div>
        <DataTable columns={scheduleCols} rows={schedule} rowKey={(a) => a.id} loading={loading} skeletonRows={4} emptyTitle="All clear today" emptyBody={<><IconCalendar /><span>No appointments are booked for today yet.</span>{permissions.includes("appointment.create") && <button className="text-control" type="button" onClick={() => setAddApptOpen(true)}>Book the first one <span>→</span></button>}</>} />
      </section>

      <div className="dash-side-col">
        <section className="panel-card"><div className="card-heading"><div><h2>Queue</h2></div><Link className="text-link" href="/queue">View all <span>→</span></Link></div>
          {loading && queue.length === 0 ? <RowSkeleton count={3} /> : queue.length === 0 ? <div className="dashboard-empty"><IconUsers /><strong>Queue is empty</strong><span>Checked-in patients will appear here as the day fills up.</span></div> : <div className="queue-list">{queue.slice(0, 5).map((e, i) => {
            const waited = e.status === "waiting" && e.checked_in_at ? Math.max(0, Math.round((now - new Date(e.checked_in_at).getTime()) / 60000)) : null;
            const heat = waited === null ? "" : waited >= 20 ? " wait-hot" : waited >= 10 ? " wait-warm" : "";
            const num = e.priority > 0 ? <span className="priority-badge" title={`Priority ${e.priority}`}>P{e.priority}</span> : String(i + 1).padStart(2, "0");
            return <div className={`queue-row${heat}`} key={e.id}><span className="queue-num">{num}</span><div className="queue-main"><strong>{e.full_name}</strong><small>{e.checked_in_at ? <>in {time(e.checked_in_at)}{waited !== null && waited > 0 && <span className="queue-wait">{waited}m waiting</span>}</> : e.reference}</small></div><span className={`queue-state state-${e.status.replaceAll("_", "-")}`}>{e.status.replaceAll("_", " ")}</span><Link className="queue-action" href={`/queue?highlight=${e.id}`}>Start →</Link></div>;
          })}</div>}
        </section>
        <section className="panel-card quick-actions"><div className="card-heading"><div><p className="eyebrow">QUICK ACTIONS</p></div></div><div className="quick-grid"><button className="quick-btn" type="button" onClick={() => setAddApptOpen(true)}><IconPlus /> Appointment <span>→</span></button><button className="quick-btn" type="button" onClick={() => setAddPatientOpen(true)}><IconUser /> Patient <span>→</span></button><Link className="quick-btn" href="/encounters"><IconPen /> Encounter <span>→</span></Link><Link className="quick-btn" href="/billing"><IconCard /> Billing <span>→</span></Link><Link className="quick-btn" href="/finance"><IconChart /> Finance <span>→</span></Link><button className="quick-btn" type="button" onClick={() => setFollowUpOpen(true)}><IconFlag /> Follow-up <span>→</span></button></div></section>
      </div>
    </div>

    <div className="dash-bottom-grid">
      <section className="panel-card"><div className="card-heading"><div><h2>Requests</h2></div><Link className="text-link" href="/schedule?status=requested">View all <span>→</span></Link></div>
        <DataTable columns={requestCols} rows={requests.slice(0, 5)} rowKey={(a) => a.id} loading={false} emptyTitle="No pending requests" />
      </section>
      <section className="panel-card"><div className="card-heading"><div><h2>Follow-ups</h2></div><Link className="text-link" href="/operations">View all <span>→</span></Link></div>
        {followups.length === 0 ? <div className="dashboard-empty"><IconCheck /><strong>Nothing due</strong><span>Follow-ups land here the moment a task is assigned.</span></div> : <div className="followup-list">{followups.slice(0, 5).map((f) => <div className="followup-row" key={f.id}><div><strong>{f.reason || "Follow-up"}</strong><small>due {dayShort(f.due_at)} {time(f.due_at)}</small></div><span className={`pipeline-status status-${f.status === "overdue" ? "lost" : "qualified"}`}>{f.status}</span></div>)}</div>}
      </section>
      <section className="panel-card"><div className="card-heading"><div><p className="eyebrow">TREND</p><h2>This week</h2></div></div><div className="bar-chart" role="img" aria-label="Appointments by weekday">{weekBars.map((b) => <div className={`bar-col${b.today ? " bar-today" : ""}`} key={b.label}><div className="bar-track"><div className="bar-fill" style={{ height: `${b.pct}%` }} title={`${b.label}: ${b.value}`} /></div><small>{b.label}</small><b>{b.value}</b></div>)}</div></section>
    </div>
    {refreshedAt && <p className="stale-note">Updated {refreshedAt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</p>}
    {clinicSlug && <AddAppointmentDrawer open={addApptOpen} onClose={() => setAddApptOpen(false)} clinicSlug={clinicSlug} onCreated={() => void load()} />}
    <AddPatientDrawer open={addPatientOpen} onClose={() => setAddPatientOpen(false)} onCreated={() => void load()} />
    <BlockTimeDrawer open={blockTimeOpen} onClose={() => setBlockTimeOpen(false)} onCreated={() => void load()} />
    <FollowUpDrawer open={followUpOpen} onClose={() => setFollowUpOpen(false)} onCreated={() => void load()} />
  </main>;
}

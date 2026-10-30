"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
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
async function getData<T>(url: string): Promise<T | null> {
  try { return await api<T>(url); } catch { return null; }
}
const statusClass = (s: string) => `pipeline-status status-${s.replaceAll("_", "-")}`;

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
    return labels.map((l, i) => ({ label: l, value: values[i], pct: Math.round((values[i] / max) * 100) }));
  }, [appointments]);

  const kpi = (value: number | undefined) => (loading && summary === null ? "…" : value ?? "—");

  return <main className="dashboard-overview" id="overview" aria-busy={loading}>
    <div className="dash-topline"><div><h1>Today</h1></div><div className="header-actions">{permissions.includes("appointment.create") && <button className="button button-primary" type="button" onClick={() => setAddApptOpen(true)}>Book appointment <span>+</span></button>}</div></div>
    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" type="button" onClick={() => void load()}>Try again <span>→</span></button></div>}

    <div className="kpi-grid" aria-live="polite">
      <Link className="kpi-card kpi-card-blue" href="/schedule"><span className="kpi-ico kpi-ico-blue" aria-hidden="true">📅</span><div><small>Appointments</small><strong>{kpi(summary?.today_appointments)}</strong></div></Link>
      <Link className="kpi-card kpi-card-green" href="/queue"><span className="kpi-ico kpi-ico-green" aria-hidden="true">👥</span><div><small>Waiting</small><strong>{kpi(summary?.waiting_patients)}</strong></div></Link>
      <Link className="kpi-card kpi-card-amber" href="/schedule?status=requested"><span className="kpi-ico kpi-ico-amber" aria-hidden="true">🗎</span><div><small>Pending</small><strong>{kpi(summary?.pending_approvals)}</strong></div></Link>
      <Link className="kpi-card kpi-card-rose" href="/operations"><span className="kpi-ico kpi-ico-rose" aria-hidden="true">✓</span><div><small>Follow-ups</small><strong>{kpi(summary?.followups_due)}</strong></div></Link>
    </div>

    <div className="dash-main-grid">
      <section className="panel-card" id="schedule"><div className="card-heading"><div><h2>Schedule</h2></div><Link className="text-link" href="/schedule">Full calendar <span>→</span></Link></div>
        <DataTable columns={scheduleCols} rows={schedule} rowKey={(a) => a.id} loading={loading} skeletonRows={4} emptyTitle="All clear today" />
      </section>

      <div className="dash-side-col">
        <section className="panel-card"><div className="card-heading"><div><h2>Queue</h2></div><Link className="text-link" href="/queue">View all <span>→</span></Link></div>
          {loading && queue.length === 0 ? <RowSkeleton count={3} /> : queue.length === 0 ? <div className="dashboard-empty"><strong>Queue is empty</strong></div> : <div className="queue-list">{queue.slice(0, 5).map((e, i) => <div className="queue-row" key={e.id}><span className="queue-num">{String(i + 1).padStart(2, "0")}</span><div className="queue-main"><strong>{e.full_name}</strong><small>{e.checked_in_at ? `in ${time(e.checked_in_at)}` : e.reference}</small></div><span className={`queue-state state-${e.status.replaceAll("_", "-")}`}>{e.status.replaceAll("_", " ")}</span><Link className="queue-action" href={`/queue?highlight=${e.id}`}>Start →</Link></div>)}</div>}
        </section>
        <section className="panel-card quick-actions"><div className="card-heading"><div><p className="eyebrow">QUICK ACTIONS</p></div></div><div className="quick-grid"><button className="quick-btn" type="button" onClick={() => setAddApptOpen(true)}>＋ Appointment <span>→</span></button><button className="quick-btn" type="button" onClick={() => setAddPatientOpen(true)}>👤 Patient <span>→</span></button><Link className="quick-btn" href="/encounters">✍ Encounter <span>→</span></Link><Link className="quick-btn" href="/billing">₿ Billing <span>→</span></Link><Link className="quick-btn" href="/finance">∑ Finance <span>→</span></Link><button className="quick-btn" type="button" onClick={() => setFollowUpOpen(true)}>🗎 Follow-up <span>→</span></button></div></section>
      </div>
    </div>

    <div className="dash-bottom-grid">
      <section className="panel-card"><div className="card-heading"><div><h2>Requests</h2></div><Link className="text-link" href="/schedule?status=requested">View all <span>→</span></Link></div>
        <DataTable columns={requestCols} rows={requests.slice(0, 5)} rowKey={(a) => a.id} loading={false} emptyTitle="No pending requests" />
      </section>
      <section className="panel-card"><div className="card-heading"><div><h2>Follow-ups</h2></div><Link className="text-link" href="/operations">View all <span>→</span></Link></div>
        {followups.length === 0 ? <div className="dashboard-empty"><strong>Nothing due</strong></div> : <div className="followup-list">{followups.slice(0, 5).map((f) => <div className="followup-row" key={f.id}><div><strong>{f.reason || "Follow-up"}</strong><small>due {dayShort(f.due_at)} {time(f.due_at)}</small></div><span className={`pipeline-status status-${f.status === "overdue" ? "lost" : "qualified"}`}>{f.status}</span></div>)}</div>}
      </section>
      <section className="panel-card"><div className="card-heading"><div><p className="eyebrow">TREND</p><h2>This week</h2></div></div><div className="bar-chart" role="img" aria-label="Appointments by weekday">{weekBars.map((b) => <div className="bar-col" key={b.label}><div className="bar-track"><div className="bar-fill" style={{ height: `${b.pct}%` }} title={`${b.label}: ${b.value}`} /></div><small>{b.label}</small><b>{b.value}</b></div>)}</div></section>
    </div>
    {refreshedAt && <p className="stale-note">Updated {refreshedAt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</p>}
    {clinicSlug && <AddAppointmentDrawer open={addApptOpen} onClose={() => setAddApptOpen(false)} clinicSlug={clinicSlug} onCreated={() => void load()} />}
    <AddPatientDrawer open={addPatientOpen} onClose={() => setAddPatientOpen(false)} onCreated={() => void load()} />
    <BlockTimeDrawer open={blockTimeOpen} onClose={() => setBlockTimeOpen(false)} onCreated={() => void load()} />
    <FollowUpDrawer open={followUpOpen} onClose={() => setFollowUpOpen(false)} onCreated={() => void load()} />
  </main>;
}

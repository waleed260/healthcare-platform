"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

type Appointment = { id: string; reference: string; starts_at: string; ends_at: string; status: string; source?: string };

function formatTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date(value));
}

function formatDay(value: string): string {
  return new Intl.DateTimeFormat(undefined, { weekday: "long", month: "short", day: "numeric" }).format(new Date(value));
}

export default function SchedulePage() {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const response = await fetch("/api/v1/appointments?limit=100", { credentials: "include", cache: "no-store" });
      const payload = await response.json() as { data?: Appointment[]; error?: { message?: string } };
      if (!response.ok) throw new Error(payload.error?.message ?? (response.status === 401 ? "Your session has expired. Sign in again to continue." : "The schedule could not be loaded."));
      setAppointments(payload.data ?? []);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The schedule could not be loaded."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const grouped = useMemo(() => {
    const groups = new Map<string, Appointment[]>();
    for (const appointment of appointments) {
      const key = new Date(appointment.starts_at).toDateString();
      groups.set(key, [...(groups.get(key) ?? []), appointment]);
    }
    return [...groups.values()];
  }, [appointments]);
  return <main className="dashboard-page"><header className="dash-header shell"><Link className="wordmark" href="/">care<span>/</span>fully</Link><div className="clinic-chip" aria-label="Clinic workspace session"><span className="clinic-avatar">VC</span><span>Clinic schedule</span></div></header><div className="dashboard shell"><aside className="sidebar"><p className="eyebrow">WORKSPACE</p><nav aria-label="Workspace navigation"><Link className="side-link" href="/dashboard">◈ <span>Overview</span></Link><Link className="side-link active" href="/schedule" aria-current="page">◷ <span>Schedule</span></Link><Link className="side-link" href="/patients">○ <span>Patients</span></Link><Link className="side-link" href="/queue">▣ <span>Queue</span></Link><a className="side-link" href="/dashboard#followups">↗ <span>Follow-ups</span></a><a className="side-link" href="/dashboard#website">✦ <span>Website</span></a></nav></aside><section className="dash-content schedule-content" aria-busy={loading}><div className="dash-topline"><div><p className="eyebrow">CALENDAR · SCOPED CLINIC VIEW</p><h1>Make room for <em>care.</em></h1></div><button className="button button-primary" type="button" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button></div><p className="schedule-intro">Appointments are shown in your local browser time and remain limited to the branches your role can access.</p>{error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" type="button" onClick={() => void load()}>Try again <span>→</span></button></div>}<div className="schedule-card calendar-card">{loading && appointments.length === 0 && <div className="dashboard-empty" role="status"><strong>Loading the schedule</strong><span>Checking your authorized appointments…</span></div>}{!loading && !error && appointments.length === 0 && <div className="dashboard-empty"><strong>No appointments found</strong><span>Your scoped calendar is clear for now.</span></div>}{grouped.map((items) => <section className="calendar-day" key={new Date(items[0].starts_at).toDateString()}><h2>{formatDay(items[0].starts_at)}</h2><div className="schedule-list">{items.map((appointment) => <article className="schedule-row" key={appointment.id}><time dateTime={appointment.starts_at}>{formatTime(appointment.starts_at)}</time><span className="appointment-dot" aria-hidden="true" /><div className="appointment-info"><strong>{appointment.reference}</strong><span>{appointment.status.replaceAll("_", " ")}{appointment.source ? ` · ${appointment.source}` : ""}</span></div><span className="appointment-status">ends {formatTime(appointment.ends_at)}</span><span className="row-arrow" aria-hidden="true">→</span></article>)}</div></section>)}</div></section></div></main>;
}

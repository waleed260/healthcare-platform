"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

type Summary = { today_appointments: number; pending_approvals: number; followups_due: number; waiting_patients: number };
type Appointment = { id: string; reference: string; starts_at: string; ends_at: string; status: string };
type ApiState = { summary: Summary | null; appointments: Appointment[]; loading: boolean; error: string | null; refreshedAt: Date | null };
const initialState: ApiState = { summary: null, appointments: [], loading: true, error: null, refreshedAt: null };

function responseMessage(response: Response, payload: unknown): string {
  if (payload && typeof payload === "object" && "error" in payload) {
    const message = (payload as { error?: { message?: string } }).error?.message;
    if (message) return message;
  }
  if (response.status === 401) return "Your clinic session has expired. Sign in again to continue.";
  return "The workspace could not be loaded. Try again shortly.";
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date(value));
}

export default function DashboardPage() {
  const [state, setState] = useState<ApiState>(initialState);
  const loadWorkspace = useCallback(async () => {
    setState((current) => ({ ...current, loading: true, error: null }));
    try {
      const [summaryResponse, appointmentsResponse] = await Promise.all([
        fetch("/api/v1/operations/dashboard-summary", { credentials: "include", cache: "no-store" }),
        fetch("/api/v1/appointments", { credentials: "include", cache: "no-store" }),
      ]);
      const summaryPayload = await summaryResponse.json();
      const appointmentsPayload = await appointmentsResponse.json();
      if (!summaryResponse.ok) throw new Error(responseMessage(summaryResponse, summaryPayload));
      if (!appointmentsResponse.ok) throw new Error(responseMessage(appointmentsResponse, appointmentsPayload));
      setState({ summary: summaryPayload.data as Summary, appointments: (appointmentsPayload.data ?? []) as Appointment[], loading: false, error: null, refreshedAt: new Date() });
    } catch (error) {
      setState((current) => ({ ...current, loading: false, error: error instanceof Error ? error.message : "The workspace could not be loaded." }));
    }
  }, []);
  useEffect(() => { void loadWorkspace(); }, [loadWorkspace]);

  const summary = state.summary;
  return <main className="dashboard-page">
    <header className="dash-header shell"><Link className="wordmark" href="/">care<span>/</span>fully</Link><div className="clinic-chip" aria-label="Clinic workspace session"><span className="clinic-avatar">VC</span><span>Clinic workspace</span><span className="chip-caret">⌄</span></div></header>
    <div className="dashboard shell">
      <aside className="sidebar"><p className="eyebrow">WORKSPACE</p><nav aria-label="Workspace navigation"><a className="side-link active" href="#overview" aria-current="page">◈ <span>Overview</span></a><Link className="side-link" href="/schedule">◷ <span>Schedule</span></Link><Link className="side-link" href="/patients">○ <span>Patients</span></Link><Link className="side-link" href="/queue">▣ <span>Queue</span></Link><a className="side-link" href="#followups">↗ <span>Follow-ups</span></a><a className="side-link" href="#website">✦ <span>Website</span></a></nav><div className="sidebar-bottom"><a className="side-link" href="#settings">⚙ <span>Settings</span></a><p className="build-label">Operations workspace<br /><span>Live clinic data</span><i /></p></div></aside>
      <section className="dash-content" id="overview" aria-busy={state.loading}>
        <div className="dash-topline"><div><p className="eyebrow">TODAY · CLINIC TIMEZONE</p><h1>Good morning, <em>team.</em></h1></div><button className="button button-primary" type="button" onClick={() => void loadWorkspace()}>Refresh <span>↻</span></button></div>
        {state.error && <div className="workspace-alert" role="alert"><strong>{state.error}</strong><button className="ghost-button" type="button" onClick={() => void loadWorkspace()}>Try again <span>→</span></button></div>}
        <div className="metric-grid" aria-live="polite"><div className="metric-card"><span>Today</span><strong>{state.loading && !summary ? "…" : summary?.today_appointments ?? "—"}</strong><small>appointments</small></div><div className="metric-card metric-warm"><span>Needs attention</span><strong>{state.loading && !summary ? "…" : summary?.pending_approvals ?? "—"}</strong><small>pending approvals</small></div><div className="metric-card metric-dark"><span>Follow-ups</span><strong>{state.loading && !summary ? "…" : summary?.followups_due ?? "—"}</strong><small>due now</small></div></div>
        <div className="schedule-card" id="schedule"><div className="card-heading"><div><p className="eyebrow">YOUR DAY</p><h2>Today&apos;s schedule</h2></div><button className="ghost-button" type="button" onClick={() => void loadWorkspace()}>Refresh list <span>↻</span></button></div>
          {state.loading && state.appointments.length === 0 && <div className="dashboard-empty" role="status"><strong>Loading today&apos;s schedule</strong><span>Checking the clinic workspace…</span></div>}
          {!state.loading && !state.error && state.appointments.length === 0 && <div className="dashboard-empty"><strong>No appointments found</strong><span>Your scoped schedule is clear for now.</span></div>}
          {state.appointments.length > 0 && <div className="schedule-list">{state.appointments.slice(0, 20).map((appointment) => <div className="schedule-row" key={appointment.id}><time dateTime={appointment.starts_at}>{formatTime(appointment.starts_at)}</time><span className="appointment-dot" aria-hidden="true" /><div className="appointment-info"><strong>{appointment.reference}</strong><span>{appointment.status.replaceAll("_", " ")}</span></div><span className="appointment-status">{formatTime(appointment.ends_at)}</span><span className="row-arrow" aria-hidden="true">→</span></div>)}</div>}
          {state.refreshedAt && <p className="stale-note">Updated {state.refreshedAt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</p>}
        </div>
      </section>
    </div>
  </main>;
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import anime from "animejs";
import { api, apiPage, errorMessage, post, writeHeaders } from "../_lib/client";
import { useToast } from "../_lib/toast";
import { useConfirm } from "../_lib/confirm";

type QueueEntry = { id: string; appointment_id: string; status: "waiting" | "in_consultation"; checked_in_at: string; priority: number; full_name: string; reference: string; starts_at: string; version: number };

type TodayAppointment = { id: string; reference: string; patient_name: string; starts_at: string; status: string; version: number };

function waitDuration(checkedInAt: string): string {
  const ms = Date.now() - new Date(checkedInAt).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

function isToday(dateStr: string): boolean {
  const d = new Date(dateStr);
  const now = new Date();
  return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
}

export default function QueuePage() {
  const toast = useToast();
  const confirm = useConfirm();
  const [entries, setEntries] = useState<QueueEntry[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [reorderTarget, setReorderTarget] = useState<string | null>(null);
  const [reorderPriority, setReorderPriority] = useState(0);
  const [reorderReason, setReorderReason] = useState("");

  const [showCheckIn, setShowCheckIn] = useState(false);
  const [todayAppointments, setTodayAppointments] = useState<TodayAppointment[]>([]);
  const [loadingAppointments, setLoadingAppointments] = useState(false);
  const [checkingIn, setCheckingIn] = useState<string | null>(null);

  const canManage = permissions.includes("queue.manage");

  const load = useCallback(async (cursor: string | null = null, append = false) => {
    setLoading(true); setError(null);
    try {
      const params = new URLSearchParams(); if (cursor) params.set("cursor", cursor);
      const url = "/api/v1/operations/queue" + (params.size ? "?" + params.toString() : "");
      const [session, page] = await Promise.all([
        append ? Promise.resolve(null) : api<{ permissions?: string[] }>("/api/v1/auth/me"),
        apiPage<QueueEntry>(url),
      ]);
      if (session) setPermissions(session.permissions ?? []);
      setEntries((current) => append ? [...current, ...page.data] : page.data);
      setNextCursor(page.nextCursor);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The queue could not be loaded.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const interval = setInterval(() => { void load(); }, 30000);
    return () => clearInterval(interval);
  }, [load]);

  async function loadTodayConfirmed() {
    setLoadingAppointments(true);
    try {
      const data = await api<TodayAppointment[]>("/api/v1/appointments?status=confirmed&limit=50");
      const today = (data ?? []).filter((a) => isToday(a.starts_at));
      setTodayAppointments(today);
    } catch {
      toast.error("Could not load today's appointments.");
    } finally { setLoadingAppointments(false); }
  }

  function openCheckInPanel() {
    setShowCheckIn(true);
    void loadTodayConfirmed();
  }

  async function checkInFromQueue(appt: TodayAppointment) {
    setCheckingIn(appt.id);
    try {
      await post("/api/v1/operations/queue/check-in", { appointment_id: appt.id, expected_version: appt.version });
      toast.success(`${appt.patient_name || appt.reference} checked in.`);
      setTodayAppointments((prev) => prev.filter((a) => a.id !== appt.id));
      await load();
    } catch (reason) {
      toast.error(errorMessage(reason, "Check-in failed."));
    } finally { setCheckingIn(null); }
  }

  async function advance(entry: QueueEntry) {
    setWorking(entry.id); setError(null); setNotice(null);
    const action = entry.status === "waiting" ? "start" : "complete";
    try {
      await post(`/api/v1/operations/queue/${entry.id}/${action}`, { expected_version: entry.version });
      setNotice(entry.status === "waiting" ? `${entry.full_name} is now in consultation.` : `${entry.full_name}'s consultation is complete.`);
      await load();
    } catch (reason) {
      const msg = errorMessage(reason, "The queue action could not be completed.");
      if (msg.includes("removed from the queue")) { setNotice(msg); } else { setError(msg); }
      await load();
    }
    finally { setWorking(null); }
  }

  async function reorder(entry: QueueEntry) {
    setWorking(entry.id); setError(null); setNotice(null);
    try {
      await post(`/api/v1/operations/queue/${entry.id}/reorder`, { expected_version: entry.version, priority: reorderPriority, priority_reason: reorderReason || "Priority updated" });
      setNotice(`${entry.full_name}'s priority updated to ${reorderPriority}.`);
      setReorderTarget(null); setReorderPriority(0); setReorderReason("");
      await load();
    } catch (reason) { setError(errorMessage(reason, "Priority could not be updated.")); await load(); }
    finally { setWorking(null); }
  }

  async function remove(entry: QueueEntry) {
    const ok = await confirm({ title: "Remove from queue", message: `Remove ${entry.full_name} from the queue? The appointment will return to confirmed status.`, danger: true, confirmLabel: "Remove" });
    if (!ok) return;
    setWorking(entry.id); setError(null); setNotice(null);
    try {
      await api(`/api/v1/operations/queue/${entry.id}`, { method: "DELETE", headers: writeHeaders(), body: JSON.stringify({ expected_version: entry.version }) });
      toast.success(`${entry.full_name} removed from the queue.`);
      await load();
    } catch (reason) { setError(errorMessage(reason, "The queue entry could not be removed.")); await load(); }
    finally { setWorking(null); }
  }

  const queueRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (loading || !queueRef.current) return;
    anime({ targets: queueRef.current.querySelectorAll(".queue-row, .queue-card"), opacity: [0, 1], translateY: [20, 0], duration: 450, delay: anime.stagger(35, { start: 100 }), easing: "easeOutCubic" });
  }, [loading]);

  return <section className="dash-content queue-content" ref={queueRef} aria-busy={loading}>
    <div className="dash-topline">
      <div><p className="eyebrow">RECEPTION · LIVE CLINIC FLOW</p><h1>Keep the day <em>moving.</em></h1></div>
      <div style={{ display: "flex", gap: 8 }}>
        {canManage && <button className="button button-secondary" type="button" onClick={openCheckInPanel} disabled={loadingAppointments}>Check in patient <span>+</span></button>}
        <button className="button button-primary" type="button" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button>
      </div>
    </div>
    <p className="queue-intro">A focused view of today&apos;s active queue. Names and actions appear only inside the authenticated, permission-scoped workspace.</p>

    {showCheckIn && <div className="queue-card" style={{ marginBottom: 16 }}>
      <div className="card-heading">
        <div><p className="eyebrow">CHECK IN</p><h2>Today&apos;s confirmed appointments</h2></div>
        <button className="ghost-button" type="button" onClick={() => setShowCheckIn(false)}>Close <span>✕</span></button>
      </div>
      {loadingAppointments && <div className="dashboard-empty" role="status"><strong>Loading appointments…</strong></div>}
      {!loadingAppointments && todayAppointments.length === 0 && <div className="dashboard-empty"><strong>No confirmed appointments</strong><span>All confirmed appointments for today have been checked in, or none are scheduled.</span></div>}
      {todayAppointments.length > 0 && <div className="queue-list">{todayAppointments.map((appt) => <article className="queue-row" key={appt.id}>
        <div className="queue-number" aria-hidden="true">·</div>
        <div className="queue-person">
          <strong>{appt.patient_name || appt.reference}</strong>
          <small>{appt.reference} · {new Date(appt.starts_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</small>
        </div>
        <span className="queue-state confirmed">{appt.status}</span>
        <div className="queue-actions">
          <button className="button queue-action" type="button" onClick={() => void checkInFromQueue(appt)} disabled={checkingIn === appt.id}>{checkingIn === appt.id ? "Checking in…" : "Check in"} <span>→</span></button>
        </div>
      </article>)}</div>}
      <div style={{ padding: "8px 0", textAlign: "right" }}>
        <button className="ghost-button" type="button" onClick={() => void loadTodayConfirmed()} disabled={loadingAppointments} style={{ fontSize: "0.8rem" }}>Refresh list <span>↻</span></button>
      </div>
    </div>}

    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" type="button" onClick={() => void load()}>Try again <span>→</span></button></div>}
    {notice && <div className="success-alert" role="status">{notice}</div>}

    <div className="queue-card">
      <div className="card-heading">
        <div><p className="eyebrow">ACTIVE NOW</p><h2>{entries.length ? `${entries.length} ${entries.length === 1 ? "person" : "people"}` : "Waiting room"}</h2></div>
        <span className="directory-count">Checked-in order</span>
      </div>
      {!canManage && !loading && <p className="permission-note">You can view the queue, but starting or completing consultations requires <code>queue.manage</code>.</p>}
      {loading && entries.length === 0 && <div className="dashboard-empty" role="status"><strong>Loading the queue</strong><span>Checking branch-scoped entries…</span></div>}
      {!loading && !error && entries.length === 0 && <div className="dashboard-empty"><strong>The queue is clear</strong><span>Checked-in patients will appear here. Use the &quot;Check in patient&quot; button above to add patients from today&apos;s confirmed appointments.</span></div>}
      {entries.length > 0 && <div className="queue-list">{entries.map((entry) => <article className="queue-row" key={entry.id}>
        <div className="queue-number" aria-hidden="true">{entry.priority > 0 ? <span className="priority-badge" title={`Priority ${entry.priority}`}>P{entry.priority}</span> : "·"}</div>
        <div className="queue-person">
          <strong>{entry.full_name}</strong>
          <small>{entry.reference} · checked in {new Date(entry.checked_in_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })} · waiting {waitDuration(entry.checked_in_at)}</small>
        </div>
        <span className={`queue-state ${entry.status}`}>{entry.status.replaceAll("_", " ")}</span>
        <div className="queue-actions">
          {canManage && <button className="ghost-button" type="button" onClick={() => { setReorderTarget(reorderTarget === entry.id ? null : entry.id); setReorderPriority(entry.priority); setReorderReason(""); }} title="Set priority">P</button>}
          <button className="button queue-action" type="button" onClick={() => void advance(entry)} disabled={!canManage || working === entry.id} title={!canManage ? "Requires queue.manage" : undefined}>{working === entry.id ? "Working…" : entry.status === "waiting" ? "Start consultation" : "Complete"}<span>→</span></button>
          {canManage && <button className="ghost-button queue-remove" type="button" onClick={() => void remove(entry)} disabled={working === entry.id} title="Remove from queue">✕</button>}
        </div>
        {reorderTarget === entry.id && <div className="reorder-inline">
          <label>Priority<input type="number" min={0} max={100} value={reorderPriority} onChange={(e) => setReorderPriority(Number(e.target.value))} /></label>
          <label>Reason<input value={reorderReason} onChange={(e) => setReorderReason(e.target.value)} placeholder="Urgent walk-in, etc." /></label>
          <button className="button button-secondary" type="button" onClick={() => void reorder(entry)} disabled={working === entry.id}>{working === entry.id ? "Saving…" : "Update priority"}</button>
          <button className="ghost-button" type="button" onClick={() => setReorderTarget(null)}>Cancel</button>
        </div>}
      </article>)}</div>}
      {nextCursor && !error && <button className="button button-secondary queue-load-more" type="button" onClick={() => void load(nextCursor, true)} disabled={loading} aria-label="Load more queue entries">{loading ? "Loading…" : "Load more entries"}<span>↓</span></button>}
    </div>
  </section>;
}

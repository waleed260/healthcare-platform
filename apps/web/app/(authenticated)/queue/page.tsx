"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import anime from "animejs";
import { api, errorMessage, post, writeHeaders } from "../_lib/client";
import { useToast } from "../_lib/toast";
import { useConfirm } from "../_lib/confirm";

type QueueEntry = { id: string; appointment_id: string; status: "waiting" | "in_consultation"; checked_in_at: string; priority: number; full_name: string; reference: string; starts_at: string; version: number };

function waitDuration(checkedInAt: string): string {
  const ms = Date.now() - new Date(checkedInAt).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
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

  const canManage = permissions.includes("queue.manage");

  const load = useCallback(async (cursor: string | null = null, append = false) => {
    setLoading(true); setError(null);
    try {
      const params = new URLSearchParams(); if (cursor) params.set("cursor", cursor);
      const url = "/api/v1/operations/queue" + (params.size ? "?" + params.toString() : "");
      const [session, entries] = await Promise.all([
        append ? Promise.resolve(null) : api<{ permissions?: string[] }>("/api/v1/auth/me"),
        api<QueueEntry[]>(url),
      ]);
      if (session) setPermissions(session.permissions ?? []);
      setEntries((current) => append ? [...current, ...(entries ?? [])] : (entries ?? []));
      setNextCursor(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The queue could not be loaded.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const interval = setInterval(() => { void load(); }, 30000);
    return () => clearInterval(interval);
  }, [load]);

  async function advance(entry: QueueEntry) {
    setWorking(entry.id); setError(null); setNotice(null);
    const action = entry.status === "waiting" ? "start" : "complete";
    try {
      await post(`/api/v1/operations/queue/${entry.id}/${action}`, { expected_version: entry.version });
      setNotice(entry.status === "waiting" ? `${entry.full_name} is now in consultation.` : `${entry.full_name}'s consultation is complete.`);
      await load();
    } catch (reason) { setError(errorMessage(reason, "The queue action could not be completed.")); }
    finally { setWorking(null); }
  }

  async function reorder(entry: QueueEntry) {
    setWorking(entry.id); setError(null); setNotice(null);
    try {
      await post(`/api/v1/operations/queue/${entry.id}/reorder`, { expected_version: entry.version, priority: reorderPriority, priority_reason: reorderReason || "Priority updated" });
      setNotice(`${entry.full_name}'s priority updated to ${reorderPriority}.`);
      setReorderTarget(null); setReorderPriority(0); setReorderReason("");
      await load();
    } catch (reason) { setError(errorMessage(reason, "Priority could not be updated.")); }
    finally { setWorking(null); }
  }

  async function remove(entry: QueueEntry) {
    const ok = await confirm({ title: "Remove from queue", message: `Remove ${entry.full_name} from the queue? The appointment will remain on the schedule.`, danger: true, confirmLabel: "Remove" });
    if (!ok) return;
    setWorking(entry.id); setError(null); setNotice(null);
    try {
      await api(`/api/v1/operations/queue/${entry.id}`, { method: "DELETE", headers: writeHeaders(), body: JSON.stringify({ expected_version: entry.version }) });
      toast.success(`${entry.full_name} removed from the queue.`);
      await load();
    } catch (reason) { setError(errorMessage(reason, "The queue entry could not be removed.")); }
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
      <button className="button button-primary" type="button" onClick={() => void load()} disabled={loading}>Refresh <span>↻</span></button>
    </div>
    <p className="queue-intro">A focused view of today&apos;s active queue. Names and actions appear only inside the authenticated, permission-scoped workspace.</p>
    {error && <div className="workspace-alert" role="alert"><strong>{error}</strong><button className="ghost-button" type="button" onClick={() => void load()}>Try again <span>→</span></button></div>}
    {notice && <div className="success-alert" role="status">{notice}</div>}

    <div className="queue-card">
      <div className="card-heading">
        <div><p className="eyebrow">ACTIVE NOW</p><h2>{entries.length ? `${entries.length} ${entries.length === 1 ? "person" : "people"}` : "Waiting room"}</h2></div>
        <span className="directory-count">Checked-in order</span>
      </div>
      {!canManage && !loading && <p className="permission-note">You can view the queue, but starting or completing consultations requires <code>queue.manage</code>.</p>}
      {loading && entries.length === 0 && <div className="dashboard-empty" role="status"><strong>Loading the queue</strong><span>Checking branch-scoped entries…</span></div>}
      {!loading && !error && entries.length === 0 && <div className="dashboard-empty"><strong>The queue is clear</strong><span>Checked-in patients will appear here.</span></div>}
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

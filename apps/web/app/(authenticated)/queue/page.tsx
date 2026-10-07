"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import anime from "animejs";
import { csrfToken } from "../_lib/client";

type QueueEntry = { id: string; appointment_id: string; status: "waiting" | "in_consultation"; checked_in_at: string; priority: number; full_name: string; reference: string; starts_at: string; version: number };

function waitDuration(checkedInAt: string): string {
  const ms = Date.now() - new Date(checkedInAt).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}
async function jsonOrNull(response: Response): Promise<{ data?: unknown; meta?: { next_cursor?: string | null }; error?: { message?: string } } | null> { return response.json().catch(() => null); }

export default function QueuePage() {
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
      const [sessionResponse, response] = await Promise.all([
        fetch("/api/v1/auth/me", { credentials: "include", cache: "no-store" }),
        fetch(url, { credentials: "include", cache: "no-store" }),
      ]);
      const session = await jsonOrNull(sessionResponse);
      const payload = await jsonOrNull(response);
      if (!sessionResponse.ok) throw new Error(session?.error?.message ?? "Your clinic session could not be checked. Try again.");
      if (!response.ok) throw new Error(payload?.error?.message ?? "The queue could not be loaded. Try again.");
      setPermissions((session?.data as { permissions?: string[] } | undefined)?.permissions ?? (session?.data as string[] | undefined) ?? []);
      setEntries((current) => append ? [...current, ...((payload?.data ?? []) as QueueEntry[])] : (payload?.data ?? []) as QueueEntry[]);
      setNextCursor(payload?.meta?.next_cursor ?? null);
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
      const response = await fetch(`/api/v1/operations/queue/${entry.id}/${action}`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() }, body: JSON.stringify({ expected_version: entry.version }) });
      const payload = await jsonOrNull(response);
      if (!response.ok) throw new Error(payload?.error?.message ?? "The queue entry changed. Refresh and try again.");
      setNotice(entry.status === "waiting" ? `${entry.full_name} is now in consultation.` : `${entry.full_name}'s consultation is complete.`);
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The queue action could not be completed."); }
    finally { setWorking(null); }
  }

  async function reorder(entry: QueueEntry) {
    setWorking(entry.id); setError(null); setNotice(null);
    try {
      const response = await fetch(`/api/v1/operations/queue/${entry.id}/reorder`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() }, body: JSON.stringify({ expected_version: entry.version, priority: reorderPriority, priority_reason: reorderReason || "Priority updated" }) });
      const payload = await jsonOrNull(response);
      if (!response.ok) throw new Error(payload?.error?.message ?? "Priority could not be updated.");
      setNotice(`${entry.full_name}'s priority updated to ${reorderPriority}.`);
      setReorderTarget(null); setReorderPriority(0); setReorderReason("");
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Priority could not be updated."); }
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
